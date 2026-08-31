# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""SynthID detection against the calibrated text fixtures.

Fixtures carry pre-computed token ids, so these tests need no tokenizer and no
model download — only ``transformers`` and ``torch`` for the g-value maths.
Tests that would load a tokenizer are marked ``synthid`` and stay out of the
per-PR run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from markproof.checks.synthid import (
    SynthIdOutcome,
    WatermarkConfig,
    detect_watermark,
    load_watermark_config,
)
from markproof.rules.schema import SynthIdDetectCheck, SynthIdThresholds

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "text"
_MANIFEST = _FIXTURES / "MANIFEST.json"

#: The generator calls the skip case "skipped"; the detector distinguishes *why*
#: it skipped, and "too_short" is the only reason it can be.
_ALIASES = {"skipped": "too_short"}

pytestmark = pytest.mark.skipif(
    not _MANIFEST.is_file(),
    reason="text fixtures not generated — run tests/fixtures/text/generate.py",
)


def _manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return data


def _config() -> WatermarkConfig:
    manifest = _manifest()
    return WatermarkConfig.model_validate(
        {**manifest["watermark_config"], "tokenizer": manifest["tokenizer"]["id"]}
    )


def _fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def _names(prefix: str) -> list[str]:
    return sorted(p.stem for p in _FIXTURES.glob(f"{prefix}*.json") if p.name != "MANIFEST.json")


def _detect(name: str, check: SynthIdDetectCheck | None = None) -> Any:
    fixture = _fixture(name)
    return detect_watermark(
        fixture["text"],
        check or SynthIdDetectCheck(type="synthid-detect"),
        _config(),
        token_ids=fixture["token_ids"],
    )


class TestTheMatrix:
    @pytest.mark.parametrize("name", _names("watermarked-"))
    def test_watermarked_text_is_detected(self, name: str) -> None:
        result = _detect(name)
        assert result.outcome is SynthIdOutcome.WATERMARKED
        assert result.score is not None and result.score >= 0.70

    @pytest.mark.parametrize("name", _names("unwatermarked-"))
    def test_unwatermarked_text_is_reported_as_such(self, name: str) -> None:
        result = _detect(name)
        assert result.outcome is SynthIdOutcome.NOT_WATERMARKED
        assert result.score is not None and result.score < 0.56

    @pytest.mark.parametrize("name", _names("weak-signal-"))
    def test_partly_marked_text_stays_uncertain(self, name: str) -> None:
        """The case that matters: elevated but not conclusive.

        Reporting these as watermarked would be the guessing the project exists
        to avoid; reporting them as clean would hide a half-broken pipeline.
        """
        result = _detect(name)
        assert result.outcome is SynthIdOutcome.UNCERTAIN
        assert result.score is not None
        assert 0.56 <= result.score < 0.70

    @pytest.mark.parametrize("name", _names("too-short-"))
    def test_short_text_is_skipped_never_scored(self, name: str) -> None:
        result = _detect(name)
        assert result.outcome is SynthIdOutcome.TOO_SHORT
        assert result.score is None, "a skipped sample must not carry a score"

    def test_a_marked_but_short_sample_is_still_skipped(self) -> None:
        """Length gates before content: 64 marked tokens are not enough."""
        assert _detect("too-short-64-marked").outcome is SynthIdOutcome.TOO_SHORT


class TestFixtureAgreement:
    def test_every_fixture_matches_its_declared_outcome(self) -> None:
        for path in sorted(_FIXTURES.glob("*.json")):
            if path.name == "MANIFEST.json":
                continue
            fixture = json.loads(path.read_text(encoding="utf-8"))
            expected = _ALIASES.get(fixture["expected_outcome"], fixture["expected_outcome"])
            assert _detect(path.stem).outcome.value == expected, path.name

    def test_defaults_match_the_calibration_sweep(self) -> None:
        """Guards against someone nudging the defaults away from the measurement."""
        recommended = _manifest()["thresholds"]
        check = SynthIdDetectCheck(type="synthid-detect")
        assert check.thresholds.not_watermarked_below == recommended["recommended_lower"]
        assert check.thresholds.watermarked_at == recommended["recommended_upper"]
        assert check.min_tokens == recommended["min_tokens"]


class TestThresholdsAndDetectors:
    def test_scores_are_reported_with_the_thresholds_they_were_judged_against(self) -> None:
        """A score without its thresholds cannot be re-checked by a reader."""
        result = _detect("watermarked-240")
        assert result.thresholds == (0.56, 0.70)

    def test_a_stricter_rule_can_demand_a_higher_score(self) -> None:
        strict = SynthIdDetectCheck(
            type="synthid-detect",
            thresholds=SynthIdThresholds(watermarked_at=0.95, not_watermarked_below=0.90),
        )
        result = _detect("watermarked-240", strict)
        assert result.outcome is SynthIdOutcome.NOT_WATERMARKED

    def test_a_high_score_below_a_strict_bound_is_not_called_chance_level(self) -> None:
        """The report must not misdescribe its own evidence.

        A score of 0.79 under a lower bound of 0.90 is a strict rule, not a
        text at chance level, and saying otherwise would mislead the reader.
        """
        strict = SynthIdDetectCheck(
            type="synthid-detect",
            thresholds=SynthIdThresholds(watermarked_at=0.95, not_watermarked_below=0.90),
        )
        detail = _detect("watermarked-240", strict).detail or ""
        assert "chance level" not in detail
        assert "elevated but below" in detail

    def test_min_tokens_can_be_lowered_deliberately(self) -> None:
        lenient = SynthIdDetectCheck(type="synthid-detect", min_tokens=20)
        assert _detect("too-short-24", lenient).outcome is not SynthIdOutcome.TOO_SHORT

    def test_bayesian_detector_reports_itself_unsupported(self) -> None:
        """Never silently fall back to mean-g under a different name."""
        bayesian = SynthIdDetectCheck(type="synthid-detect", detector="bayesian")
        result = _detect("watermarked-240", bayesian)
        assert result.outcome is SynthIdOutcome.UNSUPPORTED
        assert "BayesianDetectorModel" in (result.detail or "")


class TestDeterminism:
    def test_repeated_detection_is_identical(self) -> None:
        first, second = _detect("weak-signal-240"), _detect("weak-signal-240")
        assert first.model_dump_json() == second.model_dump_json()

    def test_score_matches_the_value_recorded_at_generation(self) -> None:
        """Cross-checks this implementation against the generator's own maths."""
        for name in _names("watermarked-") + _names("weak-signal-"):
            fixture = _fixture(name)
            result = _detect(name)
            assert result.score == pytest.approx(fixture["measured_mean_g"], abs=1e-4), name


class TestConfigLoading:
    def test_missing_config_names_the_problem(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="watermark config not found"):
            load_watermark_config(tmp_path / "absent.json")

    def test_malformed_config_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "wm.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_watermark_config(path)

    def test_incomplete_config_is_rejected(self, tmp_path: Path) -> None:
        """A partial config would score against the wrong parameters."""
        path = tmp_path / "wm.json"
        path.write_text(json.dumps({"ngram_len": 5}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_watermark_config(path)
