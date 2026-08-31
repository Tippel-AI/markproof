# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Disclosure check (Art. 50(1)) — does the system say it is an AI, and when?

Matches curated patterns from ``patterns/disclosure.de-en.yaml`` (regex plus
normalised substrings, Unicode-normalised, case-insensitive) against the probe
evidence, and checks the position — the disclosure has to be there before the
first user message, not somewhere further down the transcript.

Deliberately no fuzzy score: a pattern matches or it does not. Cases the
patterns cannot settle (is the wording "clear and distinguishable"?) end as WARN
with the evidence attached.

Positioning note: this lane is already occupied by notice generators and website
scanners. markproof does not *generate* disclosure text — it verifies that the
text reaches the running system.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from ruamel.yaml import YAML

from markproof.probes.base import Evidence, Turn
from markproof.rules.schema import DisclosurePatternCheck, Position

__all__ = [
    "DisclosureOutcome",
    "MatchHit",
    "Pattern",
    "PatternSet",
    "check_disclosure",
    "load_pattern_set",
    "normalise",
]

#: Guards against a pathological pattern hanging the run. Curated patterns are
#: short by design; anything longer is a mistake in the rulepack, not input.
_MAX_PATTERN_LENGTH = 500


def normalise(text: str) -> str:
    """Normalise text for comparison: NFKC, casefold, collapse whitespace.

    NFKC folds typographic variants (non-breaking spaces, full-width forms) that
    a copy-pasted disclosure notice picks up on its way through a web frontend.
    Without it, a visually identical string can fail to match.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(folded.split())


class Pattern(BaseModel):
    """One curated phrasing that does — or does not — constitute a disclosure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    lang: str = Field(pattern=r"^[a-z]{2}$")
    kind: Literal["regex", "substring"]
    value: str = Field(min_length=1, max_length=_MAX_PATTERN_LENGTH)
    note: str | None = None

    @field_validator("value")
    @classmethod
    def _compilable(cls, v: str, info: ValidationInfo) -> str:
        if info.data.get("kind") == "regex":
            try:
                re.compile(v, re.IGNORECASE | re.UNICODE)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}") from exc
        return v

    def matches(self, normalised_text: str) -> bool:
        """Whether this pattern is present in already-normalised text."""
        if self.kind == "substring":
            return normalise(self.value) in normalised_text
        return re.search(self.value, normalised_text, re.IGNORECASE | re.UNICODE) is not None


class PatternSet(BaseModel):
    """Curated positive and negative phrasings, grouped by language."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    description: str | None = None
    patterns: tuple[Pattern, ...] = Field(min_length=1)
    negative_patterns: tuple[Pattern, ...] = ()

    def for_lang(self, lang: str) -> tuple[tuple[Pattern, ...], tuple[Pattern, ...]]:
        """Positive and negative patterns for one language, in stable id order."""
        pos = tuple(sorted((p for p in self.patterns if p.lang == lang), key=lambda p: p.id))
        neg = tuple(
            sorted((p for p in self.negative_patterns if p.lang == lang), key=lambda p: p.id)
        )
        return pos, neg


class DisclosureOutcome(StrEnum):
    """What the check concluded.

    ``NEAR_MISS`` is the honest middle: the response contains a phrasing the
    curators explicitly listed as *not* a disclosure (say, "I am your
    assistant"). That is not a clean pass and not a confident fail — it is a
    judgement about wording, which belongs to a human.
    """

    DISCLOSED = "disclosed"
    NOT_DISCLOSED = "not_disclosed"
    NEAR_MISS = "near_miss"
    LATE = "late"
    NO_EVIDENCE = "no_evidence"


class MatchHit(BaseModel):
    """Which pattern matched where — the audit trail behind a verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern_id: str
    prompt_id: str
    kind: Literal["positive", "negative"]


class DisclosureResult(BaseModel):
    """Outcome plus the evidence that produced it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: DisclosureOutcome
    hits: tuple[MatchHit, ...]
    inspected_prompt_ids: tuple[str, ...]
    lang: str

    @property
    def passed(self) -> bool:
        return self.outcome is DisclosureOutcome.DISCLOSED


def load_pattern_set(path: Path) -> PatternSet:
    """Load and validate a pattern file.

    Raises:
        ValueError: if the document is not a mapping or fails validation.
    """
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return PatternSet.model_validate(raw)


def _turns_in_scope(evidence: Evidence, check: DisclosurePatternCheck) -> tuple[Turn, ...]:
    """The turns a rule is allowed to look at.

    ``prompt_ids`` wins when present: naming the prompts is how a rule about a
    *specific* question stays distinguishable from one about the opening
    response. Otherwise the position decides.
    """
    if check.prompt_ids:
        wanted = set(check.prompt_ids)
        return tuple(t for t in evidence.turns if t.prompt_id in wanted)
    if check.position is Position.BEFORE_FIRST_USER_MESSAGE:
        # Only an unprompted opening counts: a greeting the system sends before
        # the user has said anything. Rulepack validation keeps this away from
        # http-chat probes, where no such turn can exist.
        return tuple(t for t in evidence.turns if t.is_first)
    return tuple(evidence.turns[:1]) if evidence.turns else ()


def check_disclosure(
    evidence: Evidence,
    check: DisclosurePatternCheck,
    pattern_set: PatternSet,
) -> DisclosureResult:
    """Decide whether the probed system disclosed its AI nature.

    Pure function: no I/O, no clock. Ordering of hits is stable, so two runs over
    the same evidence produce identical results.
    """
    scope = _turns_in_scope(evidence, check)
    inspected = tuple(t.prompt_id for t in scope)

    if not scope:
        return DisclosureResult(
            outcome=DisclosureOutcome.NO_EVIDENCE,
            hits=(),
            inspected_prompt_ids=(),
            lang=evidence.lang,
        )

    positives, negatives = pattern_set.for_lang(evidence.lang)
    hits: list[MatchHit] = []

    for turn in scope:
        text = normalise(turn.response.content)
        for pattern in positives:
            if pattern.matches(text):
                hits.append(
                    MatchHit(pattern_id=pattern.id, prompt_id=turn.prompt_id, kind="positive")
                )
        for pattern in negatives:
            if pattern.matches(text):
                hits.append(
                    MatchHit(pattern_id=pattern.id, prompt_id=turn.prompt_id, kind="negative")
                )

    hits.sort(key=lambda h: (h.prompt_id, h.kind, h.pattern_id))
    # Count distinct patterns, not raw hits: a rule bound to several prompts
    # would otherwise reach min_matches through one pattern matching repeatedly,
    # which is one piece of evidence seen twice, not two pieces of evidence.
    distinct_positive = len({h.pattern_id for h in hits if h.kind == "positive"})

    if distinct_positive >= check.min_matches:
        outcome = DisclosureOutcome.DISCLOSED
    elif any(h.kind == "negative" for h in hits):
        outcome = DisclosureOutcome.NEAR_MISS
    elif (
        not check.prompt_ids
        and check.position is Position.BEFORE_FIRST_USER_MESSAGE
        and _disclosed_later(evidence, positives, scope)
    ):
        outcome = DisclosureOutcome.LATE
    else:
        outcome = DisclosureOutcome.NOT_DISCLOSED

    return DisclosureResult(
        outcome=outcome,
        hits=tuple(hits),
        inspected_prompt_ids=inspected,
        lang=evidence.lang,
    )


def _disclosed_later(
    evidence: Evidence, positives: tuple[Pattern, ...], scope: tuple[Turn, ...]
) -> bool:
    """Whether a disclosure appears outside the required position.

    Distinguishing "never disclosed" from "disclosed too late" matters to the
    person fixing it: the second is a timing bug, the first a missing feature.
    """
    scoped_ids = {t.prompt_id for t in scope}
    for turn in evidence.turns:
        if turn.prompt_id in scoped_ids:
            continue
        text = normalise(turn.response.content)
        if any(p.matches(text) for p in positives):
            return True
    return False
