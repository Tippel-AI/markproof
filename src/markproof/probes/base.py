# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Probe protocol and the Evidence container.

Every probe implements ``collect() -> Evidence``. Evidence is a serialisable
record of what the endpoint returned, with a SHA-256 digest per stored artefact
so that findings can reference immutable inputs.

Probes gather, they never judge. Keeping collection and evaluation apart is what
makes a run reproducible: the same evidence file re-evaluated later yields the
same findings, without touching the network again.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from markproof.rules.schema import ProbeKind

__all__ = [
    "Artifact",
    "ContentScope",
    "Evidence",
    "Message",
    "Probe",
    "ProbeError",
    "Turn",
    "sha256_hex",
]


def sha256_hex(data: bytes | str) -> str:
    """Hex SHA-256 of the given payload; text is encoded as UTF-8."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class ProbeError(RuntimeError):
    """The endpoint could not be probed at all.

    Raised for transport-level failures (DNS, TLS, timeout, non-JSON body).
    The CLI turns this into an operational finding rather than a traceback:
    an unreachable endpoint is a result, not a crash.
    """


class Role(StrEnum):
    """Who produced a message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """One message in a probed conversation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Role
    content: str


class Artifact(BaseModel):
    """A stored byte payload referenced by a finding.

    Only the digest and metadata live in the evidence file; the bytes go to the
    artefacts directory. That keeps evidence diffable while still pinning every
    referenced input.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: str | None = None
    data: bytes | None = Field(default=None, exclude=True, repr=False)
    """The payload itself, carried in memory for the checks to inspect.

    Excluded from serialisation: a report is meant to be read and diffed, and
    embedding megabytes of base64 would defeat both. The digest above is what
    ties a finding to these bytes; ``markproof run`` writes the bytes themselves
    into the artefacts directory.
    """

    @classmethod
    def of(
        cls, data: bytes, *, artifact_id: str, media_type: str, source_url: str | None = None
    ) -> Artifact:
        """Build an artefact from payload bytes, computing size and digest."""
        return cls(
            id=artifact_id,
            media_type=media_type,
            size_bytes=len(data),
            sha256=sha256_hex(data),
            source_url=source_url,
            data=data,
        )


class Turn(BaseModel):
    """A single request/response exchange with the target.

    ``prompt_id`` links back to the prompt set entry that triggered it, so a
    finding can say *which* question exposed the problem.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: str
    request: list[Message]
    response: Message
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_code: int
    artifacts: tuple[Artifact, ...] = ()

    @property
    def is_first(self) -> bool:
        """True when no user message preceded the response.

        Relevant for ``position: before_first_user_message`` — a disclosure that
        only appears after the user has spoken is late.
        """
        return not any(m.role is Role.USER for m in self.request)


class ContentScope(BaseModel):
    """The sub-region of a rendered document that holds generated content.

    Not a :class:`Turn`: a turn is an exchange, and this is a narrower reading
    of the same one. Modelling it as a second turn would make it a second
    *output*, which would quietly tighten every rule scoped to "every output" —
    a label rule would start demanding a notice inside the article body. It is
    an alternative view of one observation, so it lives beside the turns.

    Carries its own digest because it is what a text-marking finding cites: the
    page hash would point at bytes the check never scored.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    selector: str = Field(min_length=1)
    text: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def of(cls, text: str, *, selector: str) -> ContentScope:
        """Build a scope from extracted text, computing the digest."""
        return cls(selector=selector, text=text, sha256=sha256_hex(text))


class Evidence(BaseModel):
    """Everything one probe observed, ready to be evaluated or stored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    probe_id: str
    probe_kind: ProbeKind
    target_name: str
    lang: str = Field(pattern=r"^[a-z]{2}$")
    turns: tuple[Turn, ...]

    content_scope: ContentScope | None = None
    """The generated-text region, when the probe was told where to find it.

    Optional and absent by default: only a rendered document has a meaningful
    sub-region, and only the operator knows which one it is.
    """

    @property
    def first_turn(self) -> Turn | None:
        """The opening exchange, or None if the probe collected nothing."""
        return self.turns[0] if self.turns else None

    def turn_by_prompt(self, prompt_id: str) -> Turn | None:
        """Look up a turn by the prompt that produced it."""
        for turn in self.turns:
            if turn.prompt_id == prompt_id:
                return turn
        return None


@runtime_checkable
class Probe(Protocol):
    """What every probe implementation provides."""

    probe_id: str
    probe_kind: ProbeKind

    def collect(self) -> Evidence:
        """Gather evidence from the target.

        Raises:
            ProbeError: if the target could not be reached or spoke a protocol
                the probe does not understand.
        """
        ...
