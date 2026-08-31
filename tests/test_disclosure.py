# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Disclosure check in isolation, including the Unicode cases that bite in production."""

from __future__ import annotations

import pytest

from markproof.checks.disclosure import (
    DisclosureOutcome,
    PatternSet,
    check_disclosure,
    normalise,
)
from markproof.rules.schema import DisclosurePatternCheck, Position
from tests.helpers import make_evidence, make_turn


class TestNormalise:
    """Text normalisation is the foundation — if it drifts, every match drifts."""

    def test_casefolds_and_collapses_whitespace(self) -> None:
        assert normalise("Ich  BIN\teine\nKI") == "ich bin eine ki"

    def test_nfkc_folds_typographic_variants(self) -> None:
        # A non-breaking space is what a web frontend silently inserts.
        assert normalise("Ich bin eine KI") == normalise("Ich bin eine KI")  # noqa: RUF001 - the non-breaking space is the test subject

    def test_nfkc_folds_fullwidth_forms(self) -> None:
        assert normalise("ＫＩ") == "ki"  # noqa: RUF001 - ambiguous characters are the point here

    def test_german_sharp_s_casefolds_to_ss(self) -> None:
        # casefold() maps ß to ss — patterns must be written accordingly.
        assert normalise("GROSSE") == normalise("große")


class TestDisclosureOutcomes:
    def test_explicit_disclosure_passes(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        evidence = make_evidence(make_turn("opener", "Hallo! Ich bin eine KI und helfe gern."))
        result = check_disclosure(evidence, disclosure_check, pattern_set)
        assert result.outcome is DisclosureOutcome.DISCLOSED
        assert result.passed
        assert [h.pattern_id for h in result.hits] == ["de-explicit-ki"]

    def test_missing_disclosure_fails(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        evidence = make_evidence(make_turn("opener", "Hallo! Wie kann ich helfen?"))
        result = check_disclosure(evidence, disclosure_check, pattern_set)
        assert result.outcome is DisclosureOutcome.NOT_DISCLOSED

    def test_vague_wording_is_a_near_miss_not_a_pass(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        """ "I am your assistant" is the trap: friendly, and not a disclosure."""
        evidence = make_evidence(make_turn("opener", "Guten Tag, ich bin Ihr Assistent."))
        result = check_disclosure(evidence, disclosure_check, pattern_set)
        assert result.outcome is DisclosureOutcome.NEAR_MISS
        assert not result.passed

    def test_late_disclosure_is_distinguished_from_none(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        """A timing bug and a missing feature need different fixes."""
        evidence = make_evidence(
            make_turn("opener", "Hallo! Wie kann ich helfen?"),
            make_turn("followup", "Ich bin eine KI.", with_user_message=True),
        )
        result = check_disclosure(evidence, disclosure_check, pattern_set)
        assert result.outcome is DisclosureOutcome.LATE

    def test_no_turns_in_scope_yields_no_evidence(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        evidence = make_evidence(make_turn("followup", "Ich bin eine KI.", with_user_message=True))
        result = check_disclosure(evidence, disclosure_check, pattern_set)
        assert result.outcome is DisclosureOutcome.NO_EVIDENCE

    def test_language_selects_patterns(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        """A German pattern must not rescue an English response, or vice versa."""
        evidence = make_evidence(make_turn("opener", "Hi! I am an AI assistant."), lang="en")
        assert check_disclosure(evidence, disclosure_check, pattern_set).passed

        wrong_lang = make_evidence(make_turn("opener", "Hi! I am an AI assistant."), lang="de")
        assert not check_disclosure(wrong_lang, disclosure_check, pattern_set).passed

    def test_substring_patterns_are_normalised_on_both_sides(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        """Pattern and text both go through NFKC+casefold, so case cannot break a match."""
        evidence = make_evidence(make_turn("opener", "Dies ist ein AUTOMATISIERTES SYSTEM."))
        assert check_disclosure(evidence, disclosure_check, pattern_set).passed

    def test_min_matches_is_enforced(self, pattern_set: PatternSet) -> None:
        check = DisclosurePatternCheck(
            type="disclosure-pattern",
            patterns_file="disclosure.de-en.yaml",
            position=Position.ANYWHERE_IN_FIRST_RESPONSE,
            min_matches=2,
        )
        one_match = make_evidence(make_turn("opener", "Ich bin eine KI."))
        assert not check_disclosure(one_match, check, pattern_set).passed

        two_matches = make_evidence(
            make_turn("opener", "Ich bin eine KI. Dies ist ein automatisiertes System.")
        )
        assert check_disclosure(two_matches, check, pattern_set).passed


class TestDeterminism:
    def test_repeated_evaluation_is_identical(
        self, pattern_set: PatternSet, disclosure_check: DisclosurePatternCheck
    ) -> None:
        evidence = make_evidence(
            make_turn("opener", "Ich bin eine KI. Ich bin Ihr Assistent."),
            make_turn("direct", "Ja, ich bin ein Chatbot."),
        )
        first = check_disclosure(evidence, disclosure_check, pattern_set)
        second = check_disclosure(evidence, disclosure_check, pattern_set)
        assert first.model_dump_json() == second.model_dump_json()

    def test_hits_are_sorted_stably(self, pattern_set: PatternSet) -> None:
        check = DisclosurePatternCheck(
            type="disclosure-pattern",
            patterns_file="disclosure.de-en.yaml",
            position=Position.ANYWHERE_IN_FIRST_RESPONSE,
        )
        evidence = make_evidence(
            make_turn("opener", "Ich bin eine KI und ein automatisiertes System.")
        )
        hits = check_disclosure(evidence, check, pattern_set).hits
        assert [h.pattern_id for h in hits] == sorted(h.pattern_id for h in hits)


class TestPatternValidation:
    def test_invalid_regex_is_rejected_at_load_time(self) -> None:
        from markproof.checks.disclosure import Pattern

        with pytest.raises(ValueError, match="invalid regex"):
            Pattern(id="broken", lang="de", kind="regex", value="ich bin (eine")
