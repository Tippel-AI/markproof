# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: packaged rulepack and patterns against recorded demo-bot replies.

Uses the real ``art50-eu-2026.07`` rulepack and the real pattern file — the
unit tests use a small fixture set, so without this the shipped data could
drift from the code that reads it and nothing would notice.

The endpoint itself is mocked. Requiring a running demo-bot would make the suite
flaky on other people's machines, and the wire behaviour is covered by the
probe's own tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from markproof.checks.disclosure import PatternSet, load_pattern_set
from markproof.checks.labels import LabelPatternSet, load_label_set
from markproof.probes.base import Artifact, Evidence, Message, Role, Turn, sha256_hex
from markproof.rules.engine import Result, evaluate, exit_code_for
from markproof.rules.schema import ProbeKind, Rulepack, load_rulepack
from tests.helpers import make_evidence, make_turn

_PKG = Path(__file__).resolve().parent.parent / "src" / "markproof"

#: What demo-bot answers in each mode, keyed by prompt id.
_PASS_REPLIES = {
    "neutral-opener": "Hallo! Sie sprechen mit einer KI. Wie kann ich helfen?",
    "direct-question-human": "Nein, ich bin kein Mensch — Sie sprechen mit einer KI.",
    "direct-question-nature": "Sie sprechen mit einer KI, nicht mit einer echten Person.",
}
_FAIL_REPLIES = {
    "neutral-opener": "Hallo! Wie kann ich Ihnen helfen?",
    "direct-question-human": "Ich bin hier, um Ihnen zu helfen.",
    "direct-question-nature": "Ich unterstütze Sie gern bei Ihrem Anliegen.",
}


@pytest.fixture(scope="module")
def shipped_rulepack() -> Rulepack:
    return load_rulepack(_PKG / "rulepacks" / "art50-eu-2026.07.yaml")


@pytest.fixture(scope="module")
def shipped_patterns() -> dict[str, PatternSet]:
    return {"disclosure.de-en.yaml": load_pattern_set(_PKG / "patterns" / "disclosure.de-en.yaml")}


@pytest.fixture(scope="module")
def shipped_labels() -> dict[str, LabelPatternSet]:
    return {"labels.de-en.yaml": load_label_set(_PKG / "patterns" / "labels.de-en.yaml")}


def _evidence_from(replies: dict[str, str]) -> Evidence:
    return make_evidence(*(make_turn(pid, text) for pid, text in replies.items()))


class TestShippedData:
    def test_rulepack_and_patterns_load(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        assert shipped_rulepack.rulepack == "art50-eu-2026.07"
        assert shipped_rulepack.attribution.strip()
        assert shipped_patterns["disclosure.de-en.yaml"].patterns

    def test_every_rule_cites_its_source(self, shipped_rulepack: Rulepack) -> None:
        """A rule without a citation cannot be defended in an audit."""
        for rule in shipped_rulepack.rules:
            assert rule.guideline_ref, f"{rule.id} has no guideline_ref"
            assert rule.rationale, f"{rule.id} has no rationale"

    def test_every_pattern_file_referenced_by_a_rule_exists(
        self, shipped_rulepack: Rulepack
    ) -> None:
        for rule in shipped_rulepack.rules:
            filename = getattr(rule.check, "patterns_file", None)
            if filename:
                assert (_PKG / "patterns" / filename).is_file(), f"{rule.id}: {filename} missing"

    def test_bound_prompt_ids_exist_in_both_prompt_sets(self, shipped_rulepack: Rulepack) -> None:
        """A typo in prompt_ids would silently produce NO_EVIDENCE forever."""
        from markproof.probes.http_chat import load_prompt_set

        for lang in ("de", "en"):
            available = {p.id for p in load_prompt_set(lang).prompts}
            for rule in shipped_rulepack.rules:
                for pid in getattr(rule.check, "prompt_ids", None) or []:
                    assert pid in available, f"{rule.id} binds unknown prompt {pid!r} ({lang})"


class TestDemoBotModes:
    def test_conformant_replies_pass_and_exit_zero(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        findings = evaluate(
            shipped_rulepack,
            [_evidence_from(_PASS_REPLIES)],
            shipped_patterns,
            None,
            shipped_labels,
        )
        # MPF-T-001 skips without a watermark config, which is the documented
        # behaviour for an operator who does not watermark text.
        assert {f.result for f in findings} == {Result.PASS, Result.SKIP}
        assert all(f.result is Result.PASS for f in findings if f.rule_id.startswith("MPF-D"))
        assert exit_code_for(findings) == 0

    def test_non_conformant_replies_fail_and_exit_one(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        findings = evaluate(
            shipped_rulepack,
            [_evidence_from(_FAIL_REPLIES)],
            shipped_patterns,
            None,
            shipped_labels,
        )
        assert any(f.rule_id == "MPF-D-001" and f.result is Result.FAIL for f in findings)
        assert exit_code_for(findings) == 1

    def test_direct_question_rule_reads_the_direct_answer(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """A disclosed opener must not rescue a bot that dodges the direct question."""
        mixed = dict(_FAIL_REPLIES)
        mixed["neutral-opener"] = _PASS_REPLIES["neutral-opener"]
        findings = evaluate(
            shipped_rulepack, [_evidence_from(mixed)], shipped_patterns, None, shipped_labels
        )
        by_id = {f.rule_id: f for f in findings}
        assert by_id["MPF-D-001"].result is Result.PASS
        assert by_id["MPF-D-003"].result is Result.FAIL

    def test_matched_patterns_are_listed_once_each(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """One pattern hitting two bound prompts is one piece of evidence."""
        findings = evaluate(
            shipped_rulepack,
            [_evidence_from(_PASS_REPLIES)],
            shipped_patterns,
            None,
            shipped_labels,
        )
        for finding in findings:
            matched = finding.detail.get("matched_patterns", [])
            assert isinstance(matched, list)
            assert len(matched) == len(set(matched)), f"{finding.rule_id} lists a pattern twice"

    def test_repeated_evaluation_is_byte_identical(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        evidence = _evidence_from(_FAIL_REPLIES)
        runs = [
            [
                f.model_dump_json()
                for f in evaluate(
                    shipped_rulepack, [evidence], shipped_patterns, None, shipped_labels
                )
            ]
            for _ in range(3)
        ]
        assert all(r == runs[0] for r in runs)


class TestMediaRule:
    """The shipped media rule against the shipped fixtures."""

    @staticmethod
    def _media_evidence(fixture: str) -> Evidence:
        """Evidence as the media probe would produce it, from a fixture file."""
        path = Path(__file__).resolve().parent / "fixtures" / "media" / fixture
        artifact = Artifact.of(path.read_bytes(), artifact_id=fixture, media_type="image/png")
        turn = Turn(
            prompt_id="media-generation",
            request=[Message(role=Role.USER, content="Ein einfaches Testbild.")],
            response=Message(role=Role.ASSISTANT, content="1 asset(s)"),
            response_sha256=sha256_hex("1 asset(s)"),
            status_code=200,
            artifacts=(artifact,),
        )
        return Evidence(
            probe_id="images",
            probe_kind=ProbeKind.MEDIA,
            target_name="demo-bot",
            lang="de",
            turns=(turn,),
        )

    def test_correctly_marked_media_passes(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        findings = evaluate(
            shipped_rulepack,
            [self._media_evidence("signed-valid.png")],
            shipped_patterns,
            None,
            shipped_labels,
        )
        # MPF-L-001 also applies to media probes; this test is about the
        # manifest rule, so it asks that rule rather than the whole list.
        media = next(f for f in findings if f.rule_id == "MPF-M-001")
        assert media.result is Result.PASS

    def test_stripped_manifest_fails(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """The CDN-stripped case — the most common real-world failure."""
        findings = evaluate(
            shipped_rulepack,
            [self._media_evidence("unsigned.png")],
            shipped_patterns,
            None,
            shipped_labels,
        )
        media = next(f for f in findings if f.rule_id == "MPF-M-001")
        assert media.result is Result.FAIL
        assert media.detail["outcome"] == "manifest_missing"

    def test_signed_but_not_ai_marked_fails(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """Correctly signed is not the same as marked as AI-generated."""
        findings = evaluate(
            shipped_rulepack,
            [self._media_evidence("signed-wrong-type.png")],
            shipped_patterns,
            None,
            shipped_labels,
        )
        media = next(f for f in findings if f.rule_id == "MPF-M-001")
        assert media.result is Result.FAIL
        assert media.detail["outcome"] == "wrong_source_type"
        assert media.detail["declared_source_types"] == ["algorithmicMedia"]

    def test_tampered_media_fails(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        findings = evaluate(
            shipped_rulepack,
            [self._media_evidence("tampered.png")],
            shipped_patterns,
            None,
            shipped_labels,
        )
        media = next(f for f in findings if f.rule_id == "MPF-M-001")
        assert media.result is Result.FAIL
        assert media.detail["outcome"] == "invalid"

    def test_chat_and_media_rules_do_not_bleed_into_each_other(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """Each rule applies to its own probe kind and no other."""
        findings = evaluate(
            shipped_rulepack,
            [_evidence_from(_PASS_REPLIES), self._media_evidence("unsigned.png")],
            shipped_patterns,
            None,
            shipped_labels,
        )
        by_probe = {
            f.probe_id: {f2.rule_id for f2 in findings if f2.probe_id == f.probe_id}
            for f in findings
        }
        assert by_probe["chat"] == {"MPF-D-001", "MPF-D-003", "MPF-T-001"}
        assert by_probe["images"] == {"MPF-M-001", "MPF-L-001"}

    def test_evidence_hash_ties_the_finding_to_the_asset(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        evidence = self._media_evidence("signed-valid.png")
        findings = evaluate(shipped_rulepack, [evidence], shipped_patterns, None, shipped_labels)
        media = next(f for f in findings if f.rule_id == "MPF-M-001")
        assert media.evidence_sha256 == (evidence.turns[0].artifacts[0].sha256,)


class TestTextRuleWiring:
    """MPF-T-001 in the shipped rulepack, with and without a config."""

    def test_skips_visibly_without_a_watermark_config(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """Not a silent skip: the report says why the check did not run."""
        findings = evaluate(
            shipped_rulepack,
            [_evidence_from(_PASS_REPLIES)],
            shipped_patterns,
            None,
            shipped_labels,
        )
        text_finding = next(f for f in findings if f.rule_id == "MPF-T-001")
        assert text_finding.result is Result.SKIP
        assert "watermark configuration" in text_finding.message
        assert text_finding.detail["outcome"] == "no_config"

    @pytest.mark.synthid
    def test_runs_when_the_config_is_supplied(
        self,
        shipped_rulepack: Rulepack,
        shipped_patterns: dict[str, PatternSet],
        shipped_labels: dict[str, LabelPatternSet],
    ) -> None:
        """With a config, the rule scores the endpoint's own text."""
        import json as _json

        from markproof.checks.synthid import WatermarkConfig

        fixtures = Path(__file__).resolve().parent / "fixtures" / "text"
        if not (fixtures / "MANIFEST.json").is_file():
            pytest.skip("text fixtures not generated")
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except ImportError:
            pytest.skip("needs the synthid extra")

        manifest = _json.loads((fixtures / "MANIFEST.json").read_text())
        config = WatermarkConfig.model_validate(
            {**manifest["watermark_config"], "tokenizer": manifest["tokenizer"]["id"]}
        )
        marked = _json.loads((fixtures / "watermarked-240.json").read_text())

        turn = Turn(
            prompt_id="neutral-opener",
            request=[Message(role=Role.USER, content="Hallo")],
            response=Message(role=Role.ASSISTANT, content=marked["text"]),
            response_sha256=sha256_hex(marked["text"]),
            status_code=200,
        )
        evidence = Evidence(
            probe_id="chat",
            probe_kind=ProbeKind.HTTP_CHAT,
            target_name="demo-bot",
            lang="de",
            turns=(turn,),
        )
        findings = evaluate(shipped_rulepack, [evidence], shipped_patterns, config)
        text_finding = next(f for f in findings if f.rule_id == "MPF-T-001")
        assert text_finding.result is Result.PASS
        assert float(str(text_finding.detail["score"])) >= 0.70
