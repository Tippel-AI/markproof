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
    "Check",
    "DisclosurePatternCheck",
    "ProbeKind",
    "Rule",
    "Rulepack",
    "Severity",
    "Source",
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


#: Discriminated union — M2/M3 add ``c2pa-verify`` and ``synthid-detect`` here.
Check = Annotated[DisclosurePatternCheck, Field(discriminator="type")]


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
