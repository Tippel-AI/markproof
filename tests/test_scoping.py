# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Which turns a rule may inspect — prompt binding and position validation.

Both behaviours exist because of a concrete failure: without prompt binding, a
rule about answering a direct question silently re-checks the opening response
and duplicates another rule's verdict; without the position guard, a rulepack
can pair ``before_first_user_message`` with an API probe and warn forever
instead of failing loudly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from markproof.checks.disclosure import DisclosureOutcome, PatternSet, check_disclosure
from markproof.rules.schema import (
    DisclosurePatternCheck,
    Obligation,
    Position,
    ProbeKind,
    Rule,
    Severity,
)
from tests.helpers import make_evidence, make_turn


def _check(**kwargs: object) -> DisclosurePatternCheck:
    base: dict[str, object] = {
        "type": "disclosure-pattern",
        "patterns_file": "disclosure.de-en.yaml",
    }
    base.update(kwargs)
    return DisclosurePatternCheck(**base)  # type: ignore[arg-type]


class TestPromptBinding:
    def test_prompt_ids_select_the_named_turn(self, pattern_set: PatternSet) -> None:
        """A rule about the direct question must read the direct answer."""
        evidence = make_evidence(
            make_turn("neutral-opener", "Hallo, wie kann ich helfen?"),
            make_turn("direct-question-human", "Nein, ich bin eine KI."),
        )
        result = check_disclosure(
            evidence, _check(prompt_ids=["direct-question-human"]), pattern_set
        )
        assert result.outcome is DisclosureOutcome.DISCLOSED
        assert result.inspected_prompt_ids == ("direct-question-human",)

    def test_without_binding_the_opener_is_inspected(self, pattern_set: PatternSet) -> None:
        """Contrast case: the same evidence, unbound, reads the opener instead."""
        evidence = make_evidence(
            make_turn("neutral-opener", "Hallo, wie kann ich helfen?"),
            make_turn("direct-question-human", "Nein, ich bin eine KI."),
        )
        result = check_disclosure(evidence, _check(), pattern_set)
        assert result.outcome is DisclosureOutcome.NOT_DISCLOSED
        assert result.inspected_prompt_ids == ("neutral-opener",)

    def test_bound_rule_catches_a_bot_claiming_to_be_human(self, pattern_set: PatternSet) -> None:
        """The case the whole rule exists for: the answer denies being an AI."""
        evidence = make_evidence(
            make_turn("neutral-opener", "Ich bin eine KI."),
            make_turn("direct-question-human", "Ja, ich bin ein Mensch."),
        )
        result = check_disclosure(
            evidence, _check(prompt_ids=["direct-question-human"]), pattern_set
        )
        assert result.outcome is DisclosureOutcome.NOT_DISCLOSED

    def test_several_prompts_can_be_bound(self, pattern_set: PatternSet) -> None:
        evidence = make_evidence(
            make_turn("neutral-opener", "Hallo."),
            make_turn("direct-question-human", "Nein."),
            make_turn("direct-question-nature", "Ich bin ein Chatbot."),
        )
        result = check_disclosure(
            evidence,
            _check(prompt_ids=["direct-question-human", "direct-question-nature"]),
            pattern_set,
        )
        assert result.outcome is DisclosureOutcome.DISCLOSED
        assert result.inspected_prompt_ids == ("direct-question-human", "direct-question-nature")

    def test_unknown_prompt_id_yields_no_evidence_not_a_pass(self, pattern_set: PatternSet) -> None:
        """A typo in the rulepack must never look like a clean result."""
        evidence = make_evidence(make_turn("neutral-opener", "Ich bin eine KI."))
        result = check_disclosure(evidence, _check(prompt_ids=["typo-id"]), pattern_set)
        assert result.outcome is DisclosureOutcome.NO_EVIDENCE
        assert not result.passed

    def test_empty_prompt_ids_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be an empty list"):
            _check(prompt_ids=[])


class TestPositionGuard:
    def test_before_first_user_message_rejected_for_chat_probes(self) -> None:
        """The combination that would warn on every run, forever."""
        with pytest.raises(ValidationError, match="cannot apply to 'http-chat'"):
            Rule(
                id="MPF-D-002",
                title="unprompted disclosure",
                article="Art. 50(1)",
                obligation=Obligation.AI_INTERACTION,
                applies_to=[ProbeKind.HTTP_CHAT],
                check=_check(position=Position.BEFORE_FIRST_USER_MESSAGE),
                severity=Severity.FAIL,
            )

    def test_same_position_is_fine_for_ui_probes(self) -> None:
        """A rendered widget really does greet before the user types."""
        rule = Rule(
            id="MPF-D-002",
            title="unprompted disclosure",
            article="Art. 50(1)",
            obligation=Obligation.AI_INTERACTION,
            applies_to=[ProbeKind.UI],
            check=_check(position=Position.BEFORE_FIRST_USER_MESSAGE),
            severity=Severity.WARN,
        )
        assert rule.applies_to == [ProbeKind.UI]

    def test_chat_probes_accept_the_first_response_position(self) -> None:
        rule = Rule(
            id="MPF-D-001",
            title="disclosure in first response",
            article="Art. 50(1)",
            obligation=Obligation.AI_INTERACTION,
            applies_to=[ProbeKind.HTTP_CHAT],
            check=_check(position=Position.ANYWHERE_IN_FIRST_RESPONSE),
            severity=Severity.FAIL,
        )
        assert rule.severity is Severity.FAIL
