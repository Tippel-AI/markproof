# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Rulepack schema (pydantic), exportable as JSON Schema.

A rulepack carries its id, version, ``license: CC-BY-4.0``, a mandatory
``attribution:`` line and a ``source:`` list; each rule carries id, title, the
Article it serves, a ``guideline_ref`` clause/margin number, ``applies_to``,
the ``check`` block and a severity.

The ``attribution`` field is required, not optional: it is how the CC-BY
obligation on the derived Commission material is discharged (Auflage H1). Rules
paraphrase the sources and cite clause numbers — no verbatim paragraphs in YAML.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ruamel.yaml import YAML

__all__ = [
    "C2paVerifyCheck",
    "Check",
    "DisclosurePatternCheck",
    "ProbeKind",
    "Rule",
    "Rulepack",
    "Severity",
    "Source",
    "SynthIdDetectCheck",
    "SynthIdThresholds",
    "TrustConfig",
    "load_rulepack",
]

#: Rule ids look like ``MPF-D-001``: project prefix, category, three digits.
#: D disclosure · M media marking · T text marking · L labelling · X operational.
RULE_ID_PATTERN = re.compile(r"^MPF-[DMTLX]-\d{3}$")

#: Rulepack ids are used as filenames, so keep them filesystem-safe.
RULEPACK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")


class Severity(StrEnum):
    """How a violated rule is reported.

    ``FAIL`` sets the process exit code; ``WARN`` never does. Warn is reserved
    for obligations that cannot be decided deterministically — a guessed PASS
    would be worse than an honest WARN.
    """

    FAIL = "fail"
    WARN = "warn"


class ProbeKind(StrEnum):
    """Probe types a rule can apply to."""

    HTTP_CHAT = "http-chat"
    UI = "ui"
    MEDIA = "media"


class Position(StrEnum):
    """Where in the conversation a disclosure has to appear."""

    BEFORE_FIRST_USER_MESSAGE = "before_first_user_message"
    ANYWHERE_IN_FIRST_RESPONSE = "anywhere_in_first_response"


class Source(BaseModel):
    """One citable source behind a rulepack."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    url: str | None = None


class DisclosurePatternCheck(BaseModel):
    """Deterministic pattern match for an AI disclosure.

    Matching is literal: a curated pattern either matches or it does not. There
    is no fuzzy score, because a score would need a threshold and a threshold
    that decides a compliance verdict is a guess wearing a number.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["disclosure-pattern"]
    patterns_file: str = Field(min_length=1)
    position: Position = Position.ANYWHERE_IN_FIRST_RESPONSE
    min_matches: int = Field(default=1, ge=1)
    prompt_ids: list[str] | None = None
    """Restrict the check to the answers to these prompts.

    Without it, every rule against a chat endpoint inspects the same opening
    response, so a rule about answering a *direct* question ("are you human?")
    would silently re-check the neutral opener and report the first rule twice.
    Naming the prompts makes such a rule expressible — and makes a report say
    which question exposed the problem.
    """

    @field_validator("prompt_ids")
    @classmethod
    def _non_empty_prompt_ids(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and not v:
            raise ValueError("prompt_ids must not be an empty list; omit the field instead")
        return v


class TrustConfig(BaseModel):
    """How far signer trust is evaluated.

    v1 stops at "does the signature verify against the embedded chain".
    Evaluating a signer against the official Conformance Trust List is v1.1 —
    stated here rather than implied, so a passing report is not read as more
    than it is.
    """

    model_config = ConfigDict(extra="forbid")

    allow_self_signed: bool = True


class C2paVerifyCheck(BaseModel):
    """Verify a C2PA manifest on media the endpoint delivered.

    Presence and validity are what every C2PA tool checks. The part that carries
    this project is ``require_source_type``: Article 50(2) is about content being
    marked *as AI-generated*, so a validly signed asset that declares a camera
    capture is a failure, not a pass.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["c2pa-verify"]
    accept_source_types: list[str] | None = Field(
        default_factory=lambda: [
            "trainedAlgorithmicMedia",
            "compositeWithTrainedAlgorithmicMedia",
        ]
    )
    """Digital source types that satisfy the marking obligation.

    A list rather than a single value, because Art. 50(2) reaches content that
    was generated *or manipulated*: a human-authored composite containing
    AI-generated regions is in scope, and a rulepack that could only name one
    term would have to decide that silently. Set to ``null`` to accept any
    source type and check presence and validity alone.
    """

    require_assertions: list[str] = Field(default_factory=list)
    trust: TrustConfig = Field(default_factory=TrustConfig)
    allow_remote_manifests: bool = False
    """Whether a manifest fetched over the network counts.

    Off by default: a remote manifest that a CDN can drop is exactly the
    delivery regression this tool exists to catch, and following the URL would
    also make the check non-deterministic.
    """


class SynthIdThresholds(BaseModel):
    """Where the mean-g score stops being evidence and starts being noise.

    Calibrated against a sweep of 16 seeds per cell, not taste
    (``tests/fixtures/text/generate.py --sweep``). At 100 tokens or more the
    unwatermarked maximum measured 0.519 and the watermarked minimum 0.764, so
    0.56 sits about 3.6 sigma above chance while 0.70 keeps roughly 0.06 of
    headroom below the marked population.

    The gap between them is deliberately wide: partly marked text measured
    0.586-0.657 and lands inside it rather than on a verdict. A narrower band
    would hand those texts a confident answer they have not earned.
    """

    model_config = ConfigDict(extra="forbid")

    watermarked_at: float = Field(default=0.70, ge=0.0, le=1.0)
    not_watermarked_below: float = Field(default=0.56, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> SynthIdThresholds:
        if self.not_watermarked_below >= self.watermarked_at:
            raise ValueError(
                "not_watermarked_below must be lower than watermarked_at — "
                "otherwise there is no band left for an uncertain result, and "
                "every borderline text gets a confident verdict it has not earned"
            )
        return self


class SynthIdDetectCheck(BaseModel):
    """Verify that text output carries the operator's own SynthID watermark.

    This is a self-conformance test, not detection in the wild: it needs the
    watermark configuration the operator generates with. That is a feature, not
    a limitation — a universal detector would be guessing, and a compliance
    verdict must not rest on a guess.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["synthid-detect"]
    detector: Literal["mean-g", "bayesian"] = "mean-g"
    """``mean-g`` needs only the watermark config; ``bayesian`` needs a trained
    detector model the operator must supply."""

    min_tokens: int = Field(default=100, ge=1)
    """Below this the score is noise, so short answers are skipped rather than
    guessed at. The floor is measured, not chosen: at 40 tokens the clean and
    weakly-marked populations nearly touch (0.540 against 0.565) and weakly
    marked text can reach 0.698, which any sensible upper threshold would call
    watermarked. At 100 the two populations separate cleanly."""

    thresholds: SynthIdThresholds = Field(default_factory=SynthIdThresholds)
    on_uncertain: Severity | Literal["skip"] = Severity.FAIL
    """What an inconclusive score means for the verdict. Failing by default is
    the conservative reading: an operator claiming to watermark should produce
    text that clears the bar."""


#: Discriminated union across every check type this build implements.
Check = Annotated[
    DisclosurePatternCheck | C2paVerifyCheck | SynthIdDetectCheck,
    Field(discriminator="type"),
]


class Rule(BaseModel):
    """A single machine-checkable obligation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = Field(min_length=1)
    article: str = Field(min_length=1)
    guideline_ref: str | None = None
    rationale: str | None = None
    applies_to: list[ProbeKind] = Field(min_length=1)
    check: Check
    severity: Severity = Severity.FAIL

    @field_validator("id")
    @classmethod
    def _valid_rule_id(cls, v: str) -> str:
        if not RULE_ID_PATTERN.match(v):
            raise ValueError(
                f"rule id {v!r} must look like MPF-D-001 (category one of D, M, T, L, X)"
            )
        return v

    @field_validator("applies_to")
    @classmethod
    def _unique_probe_kinds(cls, v: list[ProbeKind]) -> list[ProbeKind]:
        if len(set(v)) != len(v):
            raise ValueError("applies_to must not repeat a probe kind")
        return v

    @model_validator(mode="after")
    def _position_matches_probe_kind(self) -> Rule:
        """Reject a combination that could only ever produce a non-verdict.

        An HTTP chat endpoint has no unprompted greeting: every turn starts with
        the probe's own message, so ``before_first_user_message`` finds nothing
        to inspect and the rule warns on every run forever. That reads like a
        cautious tool and is really a rulepack bug, so it fails loudly at load
        time. The position belongs to rendered interfaces, where a widget really
        does greet first.
        """
        position = getattr(self.check, "position", None)
        if (
            position is Position.BEFORE_FIRST_USER_MESSAGE
            and ProbeKind.HTTP_CHAT in self.applies_to
        ):
            raise ValueError(
                f"rule {self.id}: position 'before_first_user_message' cannot apply to "
                "'http-chat' — an API probe always speaks first, so the rule would "
                "never find a turn to inspect. Use 'anywhere_in_first_response', or "
                "restrict applies_to to 'ui'."
            )
        return self


class Rulepack(BaseModel):
    """A versioned, citable set of rules derived from CC-BY material."""

    model_config = ConfigDict(extra="forbid")

    rulepack: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    license: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    source: list[Source] = Field(min_length=1)
    rules: list[Rule] = Field(min_length=1)

    @field_validator("rulepack")
    @classmethod
    def _valid_rulepack_id(cls, v: str) -> str:
        if not RULEPACK_ID_PATTERN.match(v):
            raise ValueError(
                f"rulepack id {v!r} must be lowercase alphanumeric with - or . separators"
            )
        return v

    @field_validator("attribution")
    @classmethod
    def _attribution_is_substantive(cls, v: str) -> str:
        # Guards against an attribution field that technically exists but says
        # nothing — the CC-BY obligation needs a real credit line.
        if len(v.strip()) < 40:
            raise ValueError(
                "attribution must name the source work and its licence "
                "(CC-BY obligation, see NOTICE)"
            )
        return v

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> Rulepack:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id {rule.id!r}")
            seen.add(rule.id)
        return self

    def rules_for(self, probe_kind: ProbeKind) -> list[Rule]:
        """Rules applying to one probe kind, in stable id order."""
        return sorted(
            (r for r in self.rules if probe_kind in r.applies_to),
            key=lambda r: r.id,
        )


def load_rulepack(path: Path) -> Rulepack:
    """Load and validate a rulepack from YAML.

    Raises:
        ValueError: if the file is empty, malformed, or its id does not match
            the filename — a mismatch there makes reports cite a pack that
            cannot be found again.
    """
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")

    pack = Rulepack.model_validate(raw)

    expected_id = path.stem
    if pack.rulepack != expected_id:
        raise ValueError(
            f"{path}: rulepack id {pack.rulepack!r} does not match filename {expected_id!r}"
        )
    return pack
