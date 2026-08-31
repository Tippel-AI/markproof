# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""What the signature actually covers.

A signed report is the project's deliverable, so the interesting question is not
"does Ed25519 work" but "what does this signature let a reader conclude". These
tests pin the subject of the claim: which rules produced the verdict, and which
system it was produced about.
"""

from __future__ import annotations

import json
from pathlib import Path


class TestTheReportBindsWhatItJudges:
    """A signature over a document that names no subject proves very little.

    The report used to record a rulepack as four strings — id, version, licence,
    attribution — and the endpoint not at all. Since ``_resolve_rulepack`` prefers
    any local file over the packaged pack and ``load_rulepack`` only checks the id
    against the *filename*, a copy of the shipped pack with every
    ``severity: fail`` rewritten to ``warn`` produced a byte-identical header. The
    signature then attested to a verdict reached under rules nobody could
    reconstruct, about a system nobody could identify.
    """

    @staticmethod
    def _packaged() -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "src"
            / "markproof"
            / "rulepacks"
            / "art50-eu-2026.07.yaml"
        )

    def test_a_rewritten_rulepack_is_visible_in_the_report(self, tmp_path: Path) -> None:
        """The exact substitution the old header could not distinguish."""
        from markproof.report.model import build_report
        from markproof.rules.schema import load_rulepack

        original = self._packaged()
        forged = tmp_path / original.name  # same id, same filename, softer rules
        forged.write_text(
            original.read_text(encoding="utf-8").replace("severity: fail", "severity: warn"),
            encoding="utf-8",
        )

        def header(path: Path) -> dict[str, str]:
            return build_report(
                target="t",
                rulepack=load_rulepack(path),
                findings=[],
                timestamp="2026-08-31T12:00:00+00:00",
            ).rulepack

        real, fake = header(original), header(forged)
        assert real != fake, "a softened rulepack must not produce the same report header"
        assert real["sha256"] != fake["sha256"]
        # Everything else about them is identical — which is the point.
        assert {k: v for k, v in real.items() if k != "sha256"} == {
            k: v for k, v in fake.items() if k != "sha256"
        }

    def test_the_digest_is_over_the_file_a_reader_can_fetch(self) -> None:
        import hashlib

        from markproof.rules.schema import load_rulepack

        path = self._packaged()
        assert load_rulepack(path).source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()

    def test_an_in_memory_rulepack_claims_no_digest(self, rulepack: object) -> None:
        """Better to say nothing than to invent one for a pack with no file."""
        from markproof.report.model import build_report
        from markproof.rules.schema import Rulepack

        assert isinstance(rulepack, Rulepack)
        assert rulepack.source_sha256 is None
        header = build_report(
            target="t",
            rulepack=rulepack,
            findings=[],
            timestamp="2026-08-31T12:00:00+00:00",
        ).rulepack
        assert "sha256" not in header

    def test_the_report_names_the_endpoints_it_judged(self) -> None:
        """Two deployments of one product must not produce the same document."""
        from markproof.report.model import ProbeRecord, build_report
        from markproof.rules.schema import load_rulepack

        probes = (ProbeRecord(id="chat", kind="http-chat", url="https://a.example/v1/chat"),)
        report = build_report(
            target="t",
            rulepack=load_rulepack(self._packaged()),
            findings=[],
            timestamp="2026-08-31T12:00:00+00:00",
            probes=probes,
        )
        assert report.probes == probes
        assert "a.example" in json.dumps(report.to_canonical_dict())

    def test_the_endpoints_are_covered_by_the_signature(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from markproof.report.model import ProbeRecord, build_report
        from markproof.report.sign import sign_report, verify_report
        from markproof.rules.schema import load_rulepack

        report = build_report(
            target="t",
            rulepack=load_rulepack(self._packaged()),
            findings=[],
            timestamp="2026-08-31T12:00:00+00:00",
            probes=(ProbeRecord(id="chat", kind="http-chat", url="https://a.example/v1/chat"),),
        )
        signed = sign_report(report, Ed25519PrivateKey.generate())
        assert verify_report(signed, None)[0]

        moved = signed.model_copy(
            update={"probes": (ProbeRecord(id="chat", kind="http-chat", url="https://b.example"),)}
        )
        valid, _ = verify_report(moved, None)
        assert not valid, "repointing a report at another endpoint must break the signature"
