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

import hashlib
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator
from ruamel.yaml import YAML

__all__ = [
    "Applicability",
    "C2paVerifyCheck",
    "Check",
    "DisclosurePatternCheck",
    "LabelCategory",
    "LabelPresenceCheck",
    "LabelScope",
    "Obligation",
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


class Obligation(StrEnum):
    """Which Article 50 duty a rule serves.

    Finer-grained than the Article number, and deliberately so: Art. 50(2)
    covers image, audio, video *and* text, and an operator who generates page
    copy but no images has to be able to say which half binds them. A taxonomy
    that stopped at "50(2)" would force them to accept media findings they have
    no media for, which is how a tool teaches people to ignore it.

    A rule names exactly one. Where a duty has two limbs that attach to
    different parties or facts — Art. 50(4) asks deployers for a deep fake label
    in its first subparagraph and for a disclosure on public-interest text in
    its second — they are separate members, because a target can be subject to
    one and not the other.
    """

    AI_INTERACTION = "ai-interaction"
    """Art. 50(1) — systems interacting directly with natural persons."""

    SYNTHETIC_MEDIA_MARKING = "synthetic-media-marking"
    """Art. 50(2) — machine-readable marking of generated image, audio, video."""

    SYNTHETIC_TEXT_MARKING = "synthetic-text-marking"
    """Art. 50(2) — machine-readable marking of generated text."""

    EMOTION_RECOGNITION = "emotion-recognition"
    """Art. 50(3) — informing persons exposed to emotion recognition or
    biometric categorisation."""

    DEEPFAKE_LABELLING = "deepfake-labelling"
    """Art. 50(4) first subparagraph — perceivable label on deep fake content."""

    PUBLIC_INTEREST_TEXT = "public-interest-text"
    """Art. 50(4) second subparagraph — disclosure for published text informing
    on matters of public interest."""


class Applicability(RootModel[dict[Obligation, bool]]):
    """The operator's declaration of which obligations bind this target.

    Three states per obligation, not two. *Declared applicable* and *declared
    not applicable* are both statements someone made and signed for; *undeclared*
    is the absence of one, and it must not be silently read as either. So the
    default keeps every rule running: an operator who says nothing gets exactly
    the behaviour they got before this field existed, and nobody is quietly
    opted out of a check by omission.

    The declaration travels into the signed report, which is what separates this
    from a list of rules to switch off. Switching a rule off hides a finding.
    Declaring an obligation inapplicable puts a claim on the record: a report
    that skipped the deep fake rule states, over the operator's own signature,
    that they declared no deep fakes. The scope of the test stops being an
    assumption the reader has to make.
    """

    root: dict[Obligation, bool] = {}

    def applies(self, obligation: Obligation) -> bool:
        """Whether a rule for this obligation should be evaluated.

        Only an explicit ``false`` stops it. Silence means yes.
        """
        return self.root.get(obligation, True)

    def is_declared_applicable(self, obligation: Obligation) -> bool:
        """Whether the operator explicitly claimed this obligation binds them.

        Distinct from :meth:`applies`, which is also true for silence. The
        difference is what lets a missing configuration be read as a hole in a
        claim rather than as an obligation nobody ever had.
        """
        return self.root.get(obligation, False) is True


class Position(StrEnum):
    """Where in the conversation a disclosure has to appear."""

    BEFORE_FIRST_USER_MESSAGE = "before_first_user_message"
    ANYWHERE_IN_FIRST_RESPONSE = "anywhere_in_first_response"


class LabelCategory(StrEnum):
    """Which Article 50 labelling duty a set of label patterns serves.

    Two duties, two vocabularies, and they must not rescue each other: a notice
    that a room records visitors' facial expressions is a perfectly good
    Article 50(3) disclosure and says nothing at all about a deep fake.
    """

    DEEPFAKE = "deepfake"
    """Art. 50(4) first subparagraph — AI-generated or manipulated image, audio
    or video content that constitutes a deep fake."""

    EMOTION_RECOGNITION = "emotion-recognition"
    """Art. 50(3) — deployers of emotion recognition and biometric
    categorisation systems informing the persons exposed to them."""


class LabelScope(StrEnum):
    """How many of the probed outputs have to carry the label.

    ``EVERY_OUTPUT`` is the default because Guidelines §7.2 para 143 attaches
    the duty for Article 50(2) and (4) content to *each output* with respect to
    any person exposed to it — a label on the first image says nothing about the
    second. ``ANY_OUTPUT`` exists for interfaces where one notice demonstrably
    covers a whole session, which the same paragraph allows when the person is
    reasonably likely to perceive it.
    """

    EVERY_OUTPUT = "every_output"
    ANY_OUTPUT = "any_output"


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


class LabelPresenceCheck(BaseModel):
    """Deterministic pattern match for a perceivable Article 50 label.

    Presence only. Guidelines §6.1.2 para 117 requires the deep fake disclosure
    to be understandable and perceivable without technical tools, and expressly
    refuses to let the machine-readable Article 50(2) marking stand in for it —
    so this check reads the text a person would read. What it cannot read is
    whether that text is *clear and distinguishable* (§7.1 para 142: position,
    contrast, whether it can be overlooked), nor whether the content is a deep
    fake in the first place (§6.1.1 paras 113-116). Both are judgements, which is
    why rules using this check carry ``severity: warn``.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["label-presence"]
    labels_file: str = Field(min_length=1)
    """The curated label file, e.g. ``labels.de-en.yaml``.

    Deliberately not called ``patterns_file``: that name is how the loader finds
    Article 50(1) disclosure files, and a label file validates against a
    different model. Two names keep a rulepack from silently pointing one check
    at the other's vocabulary.
    """

    category: LabelCategory
    """Which duty this rule is about. Required, with no default: a rule that did
    not say would be satisfied by whichever notice happened to be on the page."""

    scope: LabelScope = LabelScope.EVERY_OUTPUT
    min_matches: int = Field(default=1, ge=1)
    """Distinct patterns that must match *within one output* for it to count as
    labelled."""


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
    DisclosurePatternCheck | C2paVerifyCheck | SynthIdDetectCheck | LabelPresenceCheck,
    Field(discriminator="type"),
]


class Rule(BaseModel):
    """A single machine-checkable obligation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = Field(min_length=1)
    article: str = Field(min_length=1)

    obligation: Obligation
    """The duty this rule serves. Required, with no default.

    A default would have to be a guess about which obligation an unspecified
    rule serves, and that guess decides whether the rule runs against a target
    that declared the duty inapplicable. There is no safe value: too broad and
    the rule fires where it does not belong, too narrow and it goes silent where
    it does. A rulepack author knows the answer; the schema asks for it.
    """

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

    source_sha256: str | None = None
    """SHA-256 of the file this pack was loaded from, set by :func:`load_rulepack`.

    Without it a report says only which rulepack *id and version* it was judged
    against, and the loader accepts any local file whose name matches. So a copy
    of the shipped pack with every ``severity: fail`` rewritten to ``warn``
    produces a byte-identical report header — the signature then attests to a
    verdict reached under rules nobody can reconstruct. The digest is what turns
    "judged against art50-eu-2026.07 v1.0.0" into a checkable statement.

    ``None`` for a pack built in memory, which is how tests construct them; a
    report produced from one says so rather than inventing a digest.
    """

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
    # Over the file's bytes, not over the parsed model: what a reader can
    # re-compute is the file, and any difference in it — a reordered rule, a
    # changed severity, an edited citation — has to show up here.
    pack = pack.model_copy(update={"source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    expected_id = path.stem
    if pack.rulepack != expected_id:
        raise ValueError(
            f"{path}: rulepack id {pack.rulepack!r} does not match filename {expected_id!r}"
        )
    return pack
