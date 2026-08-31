# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Evaluator invariants: purity, stable ordering, honest verdicts.

These are the properties the signed report rests on. If any of them slips, a
signature stops meaning what it claims to mean.
"""

from __future__ import annotations

import pytest

from markproof.checks.disclosure import PatternSet
from markproof.rules.engine import (
    Result,
    UnsupportedCheckError,
    evaluate,
    exit_code_for,
)
from markproof.rules.schema import Obligation, ProbeKind, Rule, Rulepack, Severity
from tests.helpers import make_evidence, make_turn


@pytest.fixture
def patterns(pattern_set: PatternSet) -> dict[str, PatternSet]:
    return {"disclosure.de-en.yaml": pattern_set}


class TestVerdicts:
    def test_disclosure_present_gives_pass_and_exit_zero(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        evidence = make_evidence(make_turn("opener", "Hallo, ich bin eine KI."))
        findings = evaluate(rulepack, [evidence], patterns)
        assert [f.result for f in findings] == [Result.PASS]
        assert exit_code_for(findings) == 0

    def test_disclosure_missing_gives_fail_and_exit_one(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        evidence = make_evidence(make_turn("opener", "Hallo, wie kann ich helfen?"))
        findings = evaluate(rulepack, [evidence], patterns)
        assert [f.result for f in findings] == [Result.FAIL]
        assert exit_code_for(findings) == 1

    def test_warn_severity_never_sets_exit_code(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        """A pipeline that goes red on advisory findings teaches people to ignore it."""
        advisory = rulepack.model_copy(
            update={"rules": [rulepack.rules[0].model_copy(update={"severity": Severity.WARN})]}
        )
        evidence = make_evidence(make_turn("opener", "Hallo, wie kann ich helfen?"))
        findings = evaluate(advisory, [evidence], patterns)
        assert [f.result for f in findings] == [Result.WARN]
        assert exit_code_for(findings) == 0

    def test_near_miss_warns_even_when_severity_is_fail(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        """Ambiguous wording is a question for a human, not a confident verdict."""
        evidence = make_evidence(make_turn("opener", "Guten Tag, ich bin Ihr Assistent."))
        findings = evaluate(rulepack, [evidence], patterns)
        assert findings[0].result is Result.WARN
        assert findings[0].detail["outcome"] == "near_miss"

    def test_findings_carry_the_evidence_hash(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        turn = make_turn("opener", "Hallo, wie kann ich helfen?")
        findings = evaluate(rulepack, [make_evidence(turn)], patterns)
        assert findings[0].evidence_sha256 == (turn.response_sha256,)


class TestOrderingAndPurity:
    def test_findings_sorted_by_rule_then_probe(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        second_rule = rulepack.rules[0].model_copy(update={"id": "MPF-D-002"})
        pack = rulepack.model_copy(update={"rules": [second_rule, rulepack.rules[0]]})
        evidences = [
            make_evidence(make_turn("opener", "Hallo."), probe_id="zeta"),
            make_evidence(make_turn("opener", "Hallo."), probe_id="alpha"),
        ]
        findings = evaluate(pack, evidences, patterns)
        assert [(f.rule_id, f.probe_id) for f in findings] == [
            ("MPF-D-001", "alpha"),
            ("MPF-D-001", "zeta"),
            ("MPF-D-002", "alpha"),
            ("MPF-D-002", "zeta"),
        ]

    def test_probe_order_does_not_affect_output(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        a = make_evidence(make_turn("opener", "Ich bin eine KI."), probe_id="a")
        b = make_evidence(make_turn("opener", "Hallo."), probe_id="b")
        forward = evaluate(rulepack, [a, b], patterns)
        backward = evaluate(rulepack, [b, a], patterns)
        assert [f.model_dump_json() for f in forward] == [f.model_dump_json() for f in backward]

    def test_repeated_runs_are_byte_identical(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        """The core promise: same inputs, same bytes. This is what gets signed."""
        evidence = make_evidence(
            make_turn("opener", "Ich bin Ihr Assistent."),
            make_turn("direct", "Ja, ich bin ein Chatbot.", with_user_message=True),
        )
        runs = [
            [f.model_dump_json() for f in evaluate(rulepack, [evidence], patterns)]
            for _ in range(5)
        ]
        assert all(run == runs[0] for run in runs)

    def test_rules_not_applying_to_the_probe_kind_are_skipped_entirely(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        media_only = rulepack.model_copy(
            update={
                "rules": [rulepack.rules[0].model_copy(update={"applies_to": [ProbeKind.MEDIA]})]
            }
        )
        findings = evaluate(media_only, [make_evidence(make_turn("opener", "Hallo."))], patterns)
        assert findings == []


class TestFailureModes:
    def test_missing_pattern_file_is_a_hard_error(self, rulepack: Rulepack) -> None:
        with pytest.raises(KeyError, match="was not loaded"):
            evaluate(rulepack, [make_evidence(make_turn("opener", "Hallo."))], {})

    def test_unknown_check_type_is_never_a_silent_skip(
        self, rulepack: Rulepack, patterns: dict[str, PatternSet]
    ) -> None:
        """A rulepack must not be able to claim coverage the build cannot deliver."""

        class FutureCheck:
            type = "c2pa-verify"

        rule = Rule.model_construct(
            id="MPF-M-001",
            title="future check",
            article="Art. 50(2)",
            obligation=Obligation.SYNTHETIC_MEDIA_MARKING,
            guideline_ref=None,
            rationale=None,
            applies_to=[ProbeKind.HTTP_CHAT],
            check=FutureCheck(),
            severity=Severity.FAIL,
        )
        pack = rulepack.model_copy(update={"rules": [rule]})
        with pytest.raises(UnsupportedCheckError, match="c2pa-verify"):
            evaluate(pack, [make_evidence(make_turn("opener", "Hallo."))], patterns)
