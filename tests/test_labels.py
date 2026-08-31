# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Label presence check in isolation, plus the shipped Article 50(4) data.

Three things are worth guarding here. The pattern matrix, because a label file
that stops matching "KI-generiert" fails silently. The category and language
split, because a rule that could be satisfied by the wrong vocabulary would
report compliance the operator never earned. And the deliberate non-verdicts —
the cases where the check refuses to decide are the ones a compliance tool is
judged on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from markproof.checks.labels import (
    LabelOutcome,
    LabelPattern,
    LabelPatternSet,
    check_labels,
    load_label_set,
)
from markproof.probes.base import Evidence, Message, Role, Turn, sha256_hex
from markproof.rules.schema import (
    LabelCategory,
    LabelPresenceCheck,
    LabelScope,
    ProbeKind,
    Rule,
    Severity,
    load_rulepack,
)

_PKG = Path(__file__).resolve().parent.parent / "src" / "markproof"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def shipped_labels() -> LabelPatternSet:
    """The real curated file — the unit fixtures below cannot catch drift in it."""
    return load_label_set(_PKG / "patterns" / "labels.de-en.yaml")


@pytest.fixture
def label_set() -> LabelPatternSet:
    """A small set covering both categories, both languages, both polarities."""
    return LabelPatternSet(
        version=1,
        description="test fixture",
        patterns=(
            LabelPattern(
                id="de-df-ki",
                lang="de",
                category=LabelCategory.DEEPFAKE,
                kind="substring",
                value="KI-generiert",
            ),
            LabelPattern(
                id="de-df-synthetisch",
                lang="de",
                category=LabelCategory.DEEPFAKE,
                kind="regex",
                value=r"\bsynthetische[rnms]? (?:medien|inhalte)\b",
            ),
            LabelPattern(
                id="en-df-ai",
                lang="en",
                category=LabelCategory.DEEPFAKE,
                kind="substring",
                value="AI-generated",
            ),
            LabelPattern(
                id="de-er-emotionen",
                lang="de",
                category=LabelCategory.EMOTION_RECOGNITION,
                kind="substring",
                value="Emotionserkennung",
            ),
        ),
        negative_patterns=(
            LabelPattern(
                id="de-nf-symbolbild",
                lang="de",
                category=LabelCategory.DEEPFAKE,
                kind="substring",
                value="Symbolbild",
            ),
            LabelPattern(
                id="en-nf-stock",
                lang="en",
                category=LabelCategory.DEEPFAKE,
                kind="substring",
                value="stock photo",
            ),
        ),
    )


@pytest.fixture(scope="module")
def label_rule() -> Rule:
    """MPF-L-001 straight out of the shipped rulepack."""
    pack = load_rulepack(_PKG / "rulepacks" / "art50-eu-2026.07.yaml")
    return next(r for r in pack.rules if r.id == "MPF-L-001")


@pytest.fixture
def deepfake_check() -> LabelPresenceCheck:
    """The shape MPF-L-001 uses: every output must carry the label."""
    return LabelPresenceCheck(
        type="label-presence",
        labels_file="labels.de-en.yaml",
        category=LabelCategory.DEEPFAKE,
        scope=LabelScope.EVERY_OUTPUT,
        min_matches=1,
    )


def _turn(prompt_id: str, text: str) -> Turn:
    return Turn(
        prompt_id=prompt_id,
        request=[Message(role=Role.USER, content="Erzeuge ein Bild.")],
        response=Message(role=Role.ASSISTANT, content=text),
        response_sha256=sha256_hex(text),
        status_code=200,
    )


def _evidence(*turns: Turn, lang: str = "de") -> Evidence:
    return Evidence(
        probe_id="images",
        probe_kind=ProbeKind.MEDIA,
        target_name="test-target",
        lang=lang,
        turns=turns,
    )


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #


class TestLabelOutcomes:
    def test_present_label_passes(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        evidence = _evidence(_turn("gen", "Hinweis: KI-generiert."))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.LABELLED
        assert result.passed
        assert result.labelled_prompt_ids == ("gen",)

    def test_missing_label_is_reported(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        evidence = _evidence(_turn("gen", "Ein Bild einer Stadt bei Nacht."))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.NOT_LABELLED
        assert result.unlabelled_prompt_ids == ("gen",)

    def test_near_label_wording_is_ambiguous_not_a_miss(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """ "Symbolbild" warns against literal reading and discloses no AI origin."""
        evidence = _evidence(_turn("gen", "Symbolbild."))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.AMBIGUOUS
        assert not result.passed
        assert [h.pattern_id for h in result.hits if h.kind == "negative"] == ["de-nf-symbolbild"]

    def test_positive_match_beats_a_negative_one(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """A credit line can carry both; the disclosure is what matters."""
        evidence = _evidence(_turn("gen", "Symbolbild, KI-generiert."))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.LABELLED

    def test_no_text_is_not_the_same_as_no_label(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """Nothing to read is a non-verdict, not a finding against the operator."""
        evidence = _evidence(_turn("gen", "   "))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.NO_PERCEIVABLE_TEXT
        assert result.prompt_ids_without_text == ("gen",)
        assert result.inspected_prompt_ids == ()

    def test_no_turns_at_all_yields_no_perceivable_text(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        result = check_labels(_evidence(), deepfake_check, label_set)
        assert result.outcome is LabelOutcome.NO_PERCEIVABLE_TEXT

    def test_untexted_output_does_not_drag_down_a_labelled_one(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """An output the probe recorded no text for is excluded, not counted as a miss."""
        evidence = _evidence(_turn("first", "KI-generiert."), _turn("second", ""))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.LABELLED
        assert result.prompt_ids_without_text == ("second",)


class TestScope:
    """§7.2 para 143 attaches the duty to each output, so the default is strict."""

    def test_every_output_flags_an_unlabelled_second_output(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        evidence = _evidence(_turn("first", "KI-generiert."), _turn("second", "Ein Bild."))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.NOT_LABELLED
        assert result.labelled_prompt_ids == ("first",)
        assert result.unlabelled_prompt_ids == ("second",)

    def test_inconsistent_labelling_is_not_reported_as_ambiguous(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """Some labelled, some not, plus a near-miss: that is a bug, not ambiguity."""
        evidence = _evidence(_turn("first", "KI-generiert."), _turn("second", "Symbolbild."))
        result = check_labels(evidence, deepfake_check, label_set)
        assert result.outcome is LabelOutcome.NOT_LABELLED

    def test_any_output_accepts_a_single_labelled_output(self, label_set: LabelPatternSet) -> None:
        check = LabelPresenceCheck(
            type="label-presence",
            labels_file="labels.de-en.yaml",
            category=LabelCategory.DEEPFAKE,
            scope=LabelScope.ANY_OUTPUT,
        )
        evidence = _evidence(_turn("first", "KI-generiert."), _turn("second", "Ein Bild."))
        assert check_labels(evidence, check, label_set).outcome is LabelOutcome.LABELLED

    def test_min_matches_counts_distinct_patterns_within_one_output(
        self, label_set: LabelPatternSet
    ) -> None:
        check = LabelPresenceCheck(
            type="label-presence",
            labels_file="labels.de-en.yaml",
            category=LabelCategory.DEEPFAKE,
            min_matches=2,
        )
        one = _evidence(_turn("gen", "KI-generiert. KI-generiert."))
        assert check_labels(one, check, label_set).outcome is LabelOutcome.NOT_LABELLED

        two = _evidence(_turn("gen", "KI-generiert, synthetische Medien."))
        assert check_labels(two, check, label_set).outcome is LabelOutcome.LABELLED


class TestSeparation:
    """A rule must not be satisfied by the wrong vocabulary."""

    def test_language_selects_patterns(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        english = _evidence(_turn("gen", "AI-generated image."), lang="en")
        assert check_labels(english, deepfake_check, label_set).passed

        mislabelled = _evidence(_turn("gen", "AI-generated image."), lang="de")
        assert not check_labels(mislabelled, deepfake_check, label_set).passed

    def test_category_selects_patterns(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """An emotion-recognition notice is no answer to the deep fake duty."""
        evidence = _evidence(_turn("gen", "Hinweis: Emotionserkennung ist aktiv."))
        assert check_labels(evidence, deepfake_check, label_set).outcome is (
            LabelOutcome.NOT_LABELLED
        )

        emotion_check = LabelPresenceCheck(
            type="label-presence",
            labels_file="labels.de-en.yaml",
            category=LabelCategory.EMOTION_RECOGNITION,
        )
        assert check_labels(evidence, emotion_check, label_set).passed

    def test_a_deepfake_label_does_not_satisfy_the_emotion_rule(
        self, label_set: LabelPatternSet
    ) -> None:
        emotion_check = LabelPresenceCheck(
            type="label-presence",
            labels_file="labels.de-en.yaml",
            category=LabelCategory.EMOTION_RECOGNITION,
        )
        evidence = _evidence(_turn("gen", "KI-generiert."))
        assert not check_labels(evidence, emotion_check, label_set).passed


class TestNormalisation:
    """Shared with the disclosure check — see tests/test_disclosure.py for the base cases."""

    def test_case_and_whitespace_do_not_break_a_match(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        evidence = _evidence(_turn("gen", "HINWEIS:\n\tKI-GENERIERT"))
        assert check_labels(evidence, deepfake_check, label_set).passed

    def test_nfkc_folds_a_frontend_inserted_variant(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """A caption pipeline that swaps in a non-breaking space must not hide a label."""
        evidence = _evidence(_turn("gen", "Bildnachweis: KI-generiert"))  # noqa: RUF001 - the non-breaking space is the test subject
        assert check_labels(evidence, deepfake_check, label_set).passed

    def test_fullwidth_forms_are_folded(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """Watermarking overlays sometimes render the badge in full-width forms."""
        evidence = _evidence(_turn("gen", "ＫＩ-generiert"))  # noqa: RUF001 - full-width forms are the test subject
        assert check_labels(evidence, deepfake_check, label_set).passed


class TestDeterminism:
    def test_repeated_evaluation_is_identical(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        evidence = _evidence(
            _turn("first", "KI-generiert, synthetische Medien."),
            _turn("second", "Symbolbild."),
        )
        first = check_labels(evidence, deepfake_check, label_set)
        second = check_labels(evidence, deepfake_check, label_set)
        assert first.model_dump_json() == second.model_dump_json()

    def test_hits_are_sorted_stably(
        self, label_set: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        evidence = _evidence(_turn("gen", "Symbolbild, KI-generiert, synthetische Medien."))
        hits = check_labels(evidence, deepfake_check, label_set).hits
        assert [(h.prompt_id, h.kind, h.pattern_id) for h in hits] == sorted(
            (h.prompt_id, h.kind, h.pattern_id) for h in hits
        )


class TestPatternValidation:
    def test_invalid_regex_is_rejected_at_load_time(self) -> None:
        with pytest.raises(ValueError, match="invalid regex"):
            LabelPattern(
                id="broken",
                lang="de",
                category=LabelCategory.DEEPFAKE,
                kind="regex",
                value="ki-(generiert",
            )

    def test_category_is_required(self) -> None:
        """A pattern without a category could serve whichever rule asked first."""
        with pytest.raises(ValueError, match="category"):
            LabelPattern.model_validate(
                {"id": "x", "lang": "de", "kind": "substring", "value": "KI-generiert"}
            )

    def test_a_disclosure_file_does_not_load_as_a_label_file(self) -> None:
        """The two vocabularies must not be interchangeable by accident."""
        with pytest.raises(ValueError, match="category"):
            load_label_set(_PKG / "patterns" / "disclosure.de-en.yaml")


# --------------------------------------------------------------------------- #
# The shipped data
# --------------------------------------------------------------------------- #


class TestShippedLabelFile:
    def test_both_categories_carry_at_least_ten_patterns_per_language(
        self, shipped_labels: LabelPatternSet
    ) -> None:
        """A thin list would make a green run mean nothing."""
        for category in LabelCategory:
            for lang in ("de", "en"):
                positives, _ = shipped_labels.for_category(category, lang)
                assert len(positives) >= 10, f"{category.value}/{lang}: {len(positives)}"

    def test_every_category_has_negative_patterns_in_both_languages(
        self, shipped_labels: LabelPatternSet
    ) -> None:
        for category in LabelCategory:
            for lang in ("de", "en"):
                _, negatives = shipped_labels.for_category(category, lang)
                assert negatives, f"{category.value}/{lang} has no near-miss patterns"

    def test_every_pattern_carries_a_note(self, shipped_labels: LabelPatternSet) -> None:
        """A pattern without a cited reason cannot be defended in an audit."""
        for pattern in (*shipped_labels.patterns, *shipped_labels.negative_patterns):
            assert pattern.note, f"{pattern.id} has no note"

    def test_pattern_ids_are_unique(self, shipped_labels: LabelPatternSet) -> None:
        ids = [p.id for p in (*shipped_labels.patterns, *shipped_labels.negative_patterns)]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("de", "Hinweis: Dieses Bild wurde mit KI erstellt."),
            ("de", "KI-generiertes Bild"),
            ("de", "Künstlich erzeugtes Bild einer Stadt"),
            ("de", "Künstlich verändert"),
            ("de", "Synthetische Medien"),
            ("de", "Deepfake"),
            ("de", "AI-generiert"),
            ("de", "Von einer KI erzeugt"),
            ("de", "KI-Bildmaterial"),
            ("de", "Computergeneriert"),
            ("en", "AI-generated image"),
            ("en", "This photo was artificially generated."),
            ("en", "Artificially manipulated footage"),
            ("en", "Created with generative AI"),
            ("en", "Synthetic media"),
            ("en", "Deepfake"),
            ("en", "AI-modified"),
            ("en", "Computer-generated"),
            ("en", "AI imagery"),
            ("en", "Digitally altered using AI"),
        ],
    )
    def test_real_labels_are_recognised(
        self,
        shipped_labels: LabelPatternSet,
        deepfake_check: LabelPresenceCheck,
        lang: str,
        text: str,
    ) -> None:
        evidence = _evidence(_turn("gen", text), lang=lang)
        assert check_labels(evidence, deepfake_check, shipped_labels).passed

    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("de", "Ein Foto vom Wochenende."),
            ("de", "Das ist kein Deepfake."),
            ("de", "Bildnachweis: Getty Images."),
            ("en", "A photograph taken last summer."),
            ("en", "This is not a deepfake."),
            ("en", "This image was created by our design team."),
        ],
    )
    def test_unlabelled_text_stays_unlabelled(
        self,
        shipped_labels: LabelPatternSet,
        deepfake_check: LabelPresenceCheck,
        lang: str,
        text: str,
    ) -> None:
        evidence = _evidence(_turn("gen", text), lang=lang)
        assert check_labels(evidence, deepfake_check, shipped_labels).outcome is (
            LabelOutcome.NOT_LABELLED
        )

    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("de", "Symbolbild."),
            ("de", "Digital nachbearbeitet."),
            ("de", "Die Metadaten enthalten Content Credentials nach C2PA."),
            ("de", "Diese Website nutzt künstliche Intelligenz."),
            ("de", "Erstellt ohne künstliche Intelligenz."),
            ("en", "Stock photo."),
            ("en", "Digitally enhanced."),
            ("en", "Provenance metadata attached."),
            ("en", "This platform uses generative AI."),
            ("en", "No AI was used."),
        ],
    )
    def test_near_miss_wording_needs_human_review(
        self,
        shipped_labels: LabelPatternSet,
        deepfake_check: LabelPresenceCheck,
        lang: str,
        text: str,
    ) -> None:
        """None of these disclose artificial origin; none of them are a clean miss."""
        evidence = _evidence(_turn("gen", text), lang=lang)
        assert check_labels(evidence, deepfake_check, shipped_labels).outcome is (
            LabelOutcome.AMBIGUOUS
        )

    def test_the_c2pa_pointer_is_a_near_miss_not_a_label(
        self, shipped_labels: LabelPatternSet, deepfake_check: LabelPresenceCheck
    ) -> None:
        """Para 117: the machine-readable marking does not discharge Art. 50(4)."""
        evidence = _evidence(_turn("gen", "Dieses Bild trägt ein C2PA-Manifest."))
        result = check_labels(evidence, deepfake_check, shipped_labels)
        assert result.outcome is LabelOutcome.AMBIGUOUS
        assert "de-nf-01-nur-maschinenlesbar" in {
            h.pattern_id for h in result.hits if h.kind == "negative"
        }

    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("de", "Ihre Emotionen werden dabei analysiert."),
            ("de", "Hier erfolgt eine biometrische Kategorisierung."),
            ("de", "Die Kamera erfasst Ihre Mimik."),
            ("en", "Your facial expressions are being analysed."),
            ("en", "Biometric categorisation is in use here."),
            ("en", "This booth detects your emotions."),
        ],
    )
    def test_emotion_notices_are_recognised(
        self, shipped_labels: LabelPatternSet, lang: str, text: str
    ) -> None:
        check = LabelPresenceCheck(
            type="label-presence",
            labels_file="labels.de-en.yaml",
            category=LabelCategory.EMOTION_RECOGNITION,
        )
        evidence = _evidence(_turn("kiosk", text), lang=lang)
        assert check_labels(evidence, check, shipped_labels).passed

    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("de", "Stimmungsanalyse Ihrer Nachrichten."),
            ("de", "Dieser Bereich wird videoüberwacht."),
            ("en", "Sentiment analysis of your reviews."),
            ("en", "This area is under surveillance."),
        ],
    )
    def test_text_sentiment_and_cctv_are_not_article_50_3_notices(
        self, shipped_labels: LabelPatternSet, lang: str, text: str
    ) -> None:
        """Art. 3(39) needs biometric data; a CCTV sign says nothing about inference."""
        check = LabelPresenceCheck(
            type="label-presence",
            labels_file="labels.de-en.yaml",
            category=LabelCategory.EMOTION_RECOGNITION,
        )
        evidence = _evidence(_turn("kiosk", text), lang=lang)
        assert check_labels(evidence, check, shipped_labels).outcome is LabelOutcome.AMBIGUOUS


class TestShippedRule:
    """MPF-L-001 as the rulepack declares it."""

    def test_it_warns_rather_than_failing(self, label_rule: Rule) -> None:
        """Presence is decidable; prominence and deep-fake status are not."""
        assert label_rule.severity is Severity.WARN

    def test_it_applies_to_media_and_ui(self, label_rule: Rule) -> None:
        assert set(label_rule.applies_to) == {ProbeKind.MEDIA, ProbeKind.UI}

    def test_its_label_file_exists(self, label_rule: Rule) -> None:
        assert isinstance(label_rule.check, LabelPresenceCheck)
        assert (_PKG / "patterns" / label_rule.check.labels_file).is_file()

    def test_it_checks_the_deepfake_vocabulary(self, label_rule: Rule) -> None:
        assert isinstance(label_rule.check, LabelPresenceCheck)
        assert label_rule.check.category is LabelCategory.DEEPFAKE

    def test_it_cites_paragraph_117(self, label_rule: Rule) -> None:
        """The paragraph that makes a perceivable label a separate duty."""
        assert label_rule.guideline_ref is not None
        assert "117" in label_rule.guideline_ref
