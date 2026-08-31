# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""C2PA verification against the golden fixture matrix.

Every fixture is self-produced by ``tests/fixtures/media/generate.py`` and
verified on creation, so a failure here means the check changed behaviour, not
that a file drifted. ``MANIFEST.json`` pins the expected properties rather than
digests for signed files: a signature is not byte-reproducible, but what it
asserts is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from markproof.checks.c2pa_verify import C2paOutcome, verify_media
from markproof.rules.schema import C2paVerifyCheck, TrustConfig

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "media"
_MANIFEST = _FIXTURES / "MANIFEST.json"

#: Media types keyed by suffix, so tests state the format once.
_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".mp4": "video/mp4",
    ".wav": "audio/wav",
}

pytestmark = pytest.mark.skipif(
    not _MANIFEST.is_file(),
    reason="media fixtures not generated — run tests/fixtures/media/generate.py",
)


def _check(**kwargs: Any) -> C2paVerifyCheck:
    base: dict[str, Any] = {"type": "c2pa-verify"}
    base.update(kwargs)
    return C2paVerifyCheck(**base)


def _verify(name: str, check: C2paVerifyCheck | None = None) -> Any:
    path = _FIXTURES / name
    media_type = _TYPES[path.suffix]
    return verify_media(path.read_bytes(), media_type, check or _check(), artifact_id=name)


def _fixture_names(prefix: str) -> list[str]:
    return sorted(p.name for p in _FIXTURES.glob(f"{prefix}.*") if p.suffix in _TYPES)


class TestTheMatrix:
    """The four states, across every format the fixtures cover."""

    @pytest.mark.parametrize("name", _fixture_names("signed-valid"))
    def test_valid_and_correctly_marked_passes(self, name: str) -> None:
        result = _verify(name)
        assert result.outcome is C2paOutcome.VERIFIED
        assert result.source_type == "trainedAlgorithmicMedia"

    @pytest.mark.parametrize("name", _fixture_names("unsigned"))
    def test_unsigned_reports_a_missing_manifest(self, name: str) -> None:
        assert _verify(name).outcome is C2paOutcome.MANIFEST_MISSING

    @pytest.mark.parametrize("name", _fixture_names("tampered"))
    def test_tampered_is_detected_in_every_format(self, name: str) -> None:
        """The regression that matters most: altered bytes must not pass.

        Guards a real bug — the SDK's ``is_valid`` property reports reader
        liveness, not validity, and returns True for every file here.
        """
        result = _verify(name)
        assert result.outcome is C2paOutcome.INVALID
        assert any("mismatch" in code for code in result.failure_codes)

    @pytest.mark.parametrize("name", _fixture_names("signed-wrong-type"))
    def test_wrong_source_type_fails_despite_a_perfect_signature(self, name: str) -> None:
        """The distinction the project exists for.

        These assets are signed by the same CA, their hash bindings are intact,
        and they validate cleanly. They fail on one vocabulary entry.
        """
        result = _verify(name)
        assert result.outcome is C2paOutcome.WRONG_SOURCE_TYPE
        assert result.source_type == "algorithmicMedia"
        assert not any("mismatch" in code for code in result.failure_codes)


class TestSourceTypePolicy:
    def test_composite_counts_as_marked_by_default(self) -> None:
        """Art. 50(2) reaches content generated *or manipulated*."""
        result = _verify("signed-composite.png")
        assert result.outcome is C2paOutcome.VERIFIED
        assert result.source_type == "compositeWithTrainedAlgorithmicMedia"

    def test_a_stricter_rulepack_can_reject_composites(self) -> None:
        """The policy lives in the rulepack, not in the code."""
        strict = _check(accept_source_types=["trainedAlgorithmicMedia"])
        assert _verify("signed-composite.png", strict).outcome is C2paOutcome.WRONG_SOURCE_TYPE

    def test_a_camera_capture_claim_fails(self) -> None:
        result = _verify("signed-wrong-type-capture.png")
        assert result.outcome is C2paOutcome.WRONG_SOURCE_TYPE
        assert result.source_type == "digitalCapture"

    def test_manifest_without_any_source_type_fails(self) -> None:
        """Trusted, intact, and silent about provenance is not compliance."""
        result = _verify("signed-no-source-type.png")
        assert result.outcome is C2paOutcome.WRONG_SOURCE_TYPE
        assert result.source_type is None

    def test_presence_only_mode_accepts_any_source_type(self) -> None:
        lenient = _check(accept_source_types=None)
        assert _verify("signed-wrong-type.png", lenient).outcome is C2paOutcome.VERIFIED


class TestTrust:
    """Trust is configuration, not a property of the file."""

    def test_self_signed_accepted_when_the_rule_allows_it(self) -> None:
        assert _verify("signed-valid.png").outcome is C2paOutcome.VERIFIED

    def test_untrusted_signer_is_its_own_finding(self) -> None:
        strict = _check(trust=TrustConfig(allow_self_signed=False))
        result = _verify("signed-valid.png", strict)
        assert result.outcome is C2paOutcome.UNTRUSTED_SIGNER
        assert "signingCredential.untrusted" in result.failure_codes

    def test_tampering_outranks_trust(self) -> None:
        """An altered asset is invalid regardless of who signed it."""
        strict = _check(trust=TrustConfig(allow_self_signed=False))
        assert _verify("tampered.png", strict).outcome is C2paOutcome.INVALID


class TestRobustness:
    def test_corrupt_payload_is_unreadable_not_missing(self) -> None:
        result = verify_media(b"nowhere near a png", "image/png", _check(), artifact_id="junk")
        assert result.outcome is C2paOutcome.UNREADABLE

    def test_empty_payload_does_not_crash(self) -> None:
        result = verify_media(b"", "image/png", _check(), artifact_id="empty")
        assert result.outcome in {C2paOutcome.UNREADABLE, C2paOutcome.MANIFEST_MISSING}

    def test_repeated_verification_is_identical(self) -> None:
        first = _verify("signed-wrong-type.png")
        second = _verify("signed-wrong-type.png")
        assert first.model_dump_json() == second.model_dump_json()


class TestFixtureIntegrity:
    """The fixtures must be what their names claim."""

    def test_manifest_lists_every_media_file(self) -> None:
        listed = {e["filename"] for e in json.loads(_MANIFEST.read_text())["files"]}
        on_disk = {p.name for p in _FIXTURES.iterdir() if p.suffix in _TYPES}
        assert on_disk == listed

    def test_expectations_in_the_manifest_hold(self) -> None:
        """Cross-checks the generator's claims against this implementation."""
        for entry in json.loads(_MANIFEST.read_text())["files"]:
            name = entry["filename"]
            if Path(name).suffix not in _TYPES:
                continue
            result = _verify(name)
            if entry.get("expected_manifest_present") is False:
                assert result.outcome is C2paOutcome.MANIFEST_MISSING, name
            elif entry.get("expected_validation_state") == "Invalid":
                assert result.outcome is C2paOutcome.INVALID, name
