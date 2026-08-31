# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Label presence checks (Art. 50(4) deep fakes, Art. 50(3) emotion recognition).

Article 50(4) obliges the *deployer* to disclose the artificial origin of a deep
fake, and the Guidelines are explicit about the form: the disclosure has to be
understandable and perceivable by a person — a visible or audible label — without
them reaching for a tool (§6.1.2 para 117). The same paragraph rules out leaning
on the machine-readable marking that Article 50(2) already requires, because that
marking is not perceivable at the place where the content is shown. So this check
looks at the *text a person would read*, not at metadata: metadata is what
``checks/c2pa_verify.py`` is for, and the two obligations are deliberately
separate.

What this module does **not** decide, on purpose:

* whether the content is a deep fake at all. That is the four-criteria,
  case-by-case assessment of §6.1.1 paras 113-116 — resemblance, existence, the
  subject depicted, and whether the result would falsely appear authentic. No
  pattern match can perform it.
* whether a label that is present is *clear and distinguishable* in the sense of
  Article 50(5). §7.1 para 142 makes that a question of noticeability and
  separation from the surrounding content, and §7.2 para 143 adds placement and
  repetition over time. Position, contrast and duration do not appear in the
  text.

What is left is a question with a deterministic answer: **is a label there at
all?** A rule built on this check is therefore ``warn``, never ``fail`` — see
``docs/RULES_SOURCES.md`` §9.

Normalisation and the matching contract are shared with the Article 50(1)
disclosure check: same NFKC + casefold + whitespace collapse, same
regex/substring split, same rule that a positive match beats a negative one.
``LabelPattern`` and ``LabelPatternSet`` extend the disclosure models with a
``category`` so that one curated file can carry both labelling duties without a
rule ever mixing them up.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

from markproof.checks.disclosure import MatchHit, Pattern, PatternSet, normalise
from markproof.probes.base import Evidence, Turn
from markproof.rules.schema import (
    LabelCategory,
    LabelPresenceCheck,
    LabelScope,
    ProbeKind,
)

__all__ = [
    "LabelOutcome",
    "LabelPattern",
    "LabelPatternSet",
    "LabelResult",
    "check_labels",
    "load_label_set",
]


class LabelPattern(Pattern):
    """A curated label phrasing, tagged with the duty it serves.

    Extends the disclosure ``Pattern`` rather than restating it: the matching
    contract (NFKC + casefold, regex or normalised substring, compile-time
    validation of the regex) is identical, and duplicating it would let the two
    files drift apart while both claim to be "the same normalisation".
    """

    category: LabelCategory


class LabelPatternSet(PatternSet):
    """Curated label phrasings for both Article 50 labelling duties.

    One file, two categories. Keeping them together is deliberate: they share
    the matching contract and the CC-BY provenance, and a rule names the
    category it wants, so a deep fake rule can never be satisfied by an emotion
    recognition notice.
    """

    patterns: tuple[LabelPattern, ...] = Field(min_length=1)
    negative_patterns: tuple[LabelPattern, ...] = ()

    def for_category(
        self, category: LabelCategory, lang: str
    ) -> tuple[tuple[LabelPattern, ...], tuple[LabelPattern, ...]]:
        """Positive and negative patterns for one duty and one language.

        Sorted by id so that two runs over the same evidence emit hits in the
        same order — the report is signed, so ordering is part of the contract.
        """
        pos = tuple(
            sorted(
                (p for p in self.patterns if p.category is category and p.lang == lang),
                key=lambda p: p.id,
            )
        )
        neg = tuple(
            sorted(
                (p for p in self.negative_patterns if p.category is category and p.lang == lang),
                key=lambda p: p.id,
            )
        )
        return pos, neg


class LabelOutcome(StrEnum):
    """What the check concluded.

    Only ``LABELLED`` is a pass. The other three are the reasons a machine
    should not claim more than it saw:

    ``NOT_LABELLED``
        Text was inspected and carried no label. Under ``every_output`` this
        also covers the inconsistent case — some outputs labelled, others not —
        which is a delivery bug worth naming as such rather than folding into
        "ambiguous".
    ``AMBIGUOUS``
        Nothing positive matched anywhere, but a phrasing the curators listed as
        *not* a label did: a stock-photo notice, a blanket "this site uses AI",
        or a pointer at the C2PA metadata that §6.1.2 para 117 expressly says
        does not discharge the deployer's duty. Whether the surrounding context
        rescues it is a human judgement.
    ``NO_PERCEIVABLE_TEXT``
        The probe recorded no text for any output in scope. Nothing was checked,
        and saying "not labelled" would be an assertion about evidence that does
        not exist.
    """

    LABELLED = "labelled"
    NOT_LABELLED = "not_labelled"
    AMBIGUOUS = "ambiguous"
    NO_PERCEIVABLE_TEXT = "no_perceivable_text"


class LabelResult(BaseModel):
    """Outcome plus the evidence that produced it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: LabelOutcome
    category: LabelCategory
    lang: str
    hits: tuple[MatchHit, ...]
    inspected_prompt_ids: tuple[str, ...]
    labelled_prompt_ids: tuple[str, ...]
    unlabelled_prompt_ids: tuple[str, ...]
    prompt_ids_without_text: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.outcome is LabelOutcome.LABELLED


def load_label_set(path: Path) -> LabelPatternSet:
    """Load and validate a label pattern file.

    Mirrors ``disclosure.load_pattern_set``; separate because the model it
    validates against is different, and a loader that guessed the model from the
    file contents would accept a deep fake rule pointed at a disclosure file.

    Raises:
        ValueError: if the document is not a mapping or fails validation.
    """
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return LabelPatternSet.model_validate(raw)


def check_labels(
    evidence: Evidence,
    check: LabelPresenceCheck,
    label_set: LabelPatternSet,
) -> LabelResult:
    """Decide whether a perceivable label accompanies the probed outputs.

    Every turn is inspected, not just the first: §7.2 para 143 attaches the
    information duty for Article 50(2) and (4) content to *each output* of the
    system with respect to any person exposed to it, so a label on the opening
    output says nothing about the next one. ``check.scope`` decides what to make
    of a mixed result.

    Pure function: no I/O, no clock. Hit ordering is stable, so two runs over the
    same evidence produce identical results.
    """
    positives, negatives = label_set.for_category(check.category, evidence.lang)

    hits: list[MatchHit] = []
    labelled: list[str] = []
    unlabelled: list[str] = []
    without_text: list[str] = []

    for turn in evidence.turns:
        text = _perceivable_text(turn, evidence.probe_kind)
        if not text:
            # Not the same as "no label": there was nothing to read. Recorded
            # separately so a report can say which of the two it saw.
            without_text.append(turn.prompt_id)
            continue

        matched: set[str] = set()
        for pattern in positives:
            if pattern.matches(text):
                matched.add(pattern.id)
                hits.append(
                    MatchHit(pattern_id=pattern.id, prompt_id=turn.prompt_id, kind="positive")
                )
        for pattern in negatives:
            if pattern.matches(text):
                hits.append(
                    MatchHit(pattern_id=pattern.id, prompt_id=turn.prompt_id, kind="negative")
                )

        # Distinct patterns, not raw hits: the same pattern matching twice in one
        # output is one piece of evidence seen twice.
        if len(matched) >= check.min_matches:
            labelled.append(turn.prompt_id)
        else:
            unlabelled.append(turn.prompt_id)

    hits.sort(key=lambda h: (h.prompt_id, h.kind, h.pattern_id))

    return LabelResult(
        outcome=_outcome(check, hits, labelled, unlabelled),
        category=check.category,
        lang=evidence.lang,
        hits=tuple(hits),
        inspected_prompt_ids=tuple(labelled + unlabelled),
        labelled_prompt_ids=tuple(labelled),
        unlabelled_prompt_ids=tuple(unlabelled),
        prompt_ids_without_text=tuple(without_text),
    )


def _perceivable_text(turn: Turn, probe_kind: ProbeKind) -> str:
    """The text a person exposed to this output would read, normalised.

    Article 50(4) is about what is perceivable *where the content is displayed*,
    so this is only a faithful reading for a probe that captures a rendered
    surface. A media endpoint does not have one: its response body is an images
    API's bookkeeping — ``{"data": [{"url": …}]}`` — and the probe records a
    summary of it, ``"3 asset(s): images-0, images-1, images-2"``, so a finding
    can name what it inspected.

    That summary used to be handed to this function as if it were what a person
    reads. It is non-empty, so the "nothing to read" branch never fired; it can
    never match a label, so every media probe produced the same warning — on the
    strength of a string markproof wrote itself. A warning that appears for every
    target carries no information and teaches its reader to skip it.

    So a media probe reports no perceivable text, and the rule skips with that
    reason. The deployer-side duty in Article 50(4) is real for this content; it
    attaches to the page where the image is shown, which is a UI probe's job.
    See ``docs/RULES_SOURCES.md`` §9.3.
    """
    if probe_kind is ProbeKind.MEDIA:
        return ""
    return normalise(turn.response.content)


def _outcome(
    check: LabelPresenceCheck,
    hits: list[MatchHit],
    labelled: list[str],
    unlabelled: list[str],
) -> LabelOutcome:
    """Fold the per-output results into one verdict."""
    if not labelled and not unlabelled:
        return LabelOutcome.NO_PERCEIVABLE_TEXT

    if check.scope is LabelScope.EVERY_OUTPUT:
        if not unlabelled:
            return LabelOutcome.LABELLED
    elif labelled:
        return LabelOutcome.LABELLED

    # Ambiguity is a statement about wording, so it only applies when no output
    # carried a label at all. A run where some outputs are labelled and others
    # are not is not ambiguous — it is inconsistent, and naming it
    # NOT_LABELLED with the offending outputs listed is the more useful report.
    if not labelled and any(h.kind == "negative" for h in hits):
        return LabelOutcome.AMBIGUOUS
    return LabelOutcome.NOT_LABELLED
