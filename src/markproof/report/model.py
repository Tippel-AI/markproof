# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Report data model — one structure, several renderers.

Holds the markproof version, the rulepack id and version, the target name, run
metadata, the findings with their evidence, the PASS/FAIL/WARN/SKIP summary, and
the signature block.

The signature block records the canonicaliser and its exact version
(``"canonicalizer": "rfc8785==0.1.4"``) so the signature stays reproducible
years later. JSON, Markdown summary and both PDF renderers all read from this
model — never from each other.

Everything that varies between two runs of the same inputs lives in ``run``, and
every field there can be pinned. That is what makes the determinism test
possible: freeze ``run``, and two runs produce identical bytes.
"""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from markproof import __version__
from markproof.rules.engine import Finding, Result
from markproof.rules.schema import Applicability, Rulepack

__all__ = ["Report", "RunMetadata", "Signature", "Summary", "build_report"]

#: Report schema version. Bumped when the shape changes in a way that would
#: break a verifier written against the previous one.
REPORT_SCHEMA_VERSION = 1


class RunMetadata(BaseModel):
    """When and where the run happened.

    Every field is injectable. A signed artefact needs a timestamp to be worth
    anything, and a determinism test needs to remove it — both are satisfied by
    making the value an input rather than a side effect.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
    )
    markproof_version: str
    python_version: str
    platform: str


class Summary(BaseModel):
    """Counts per result, plus the overall verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    warned: int = Field(ge=0)
    skipped: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.warned + self.skipped

    @property
    def conformant(self) -> bool:
        """Whether nothing blocking was found.

        Deliberately not "compliant": the tool checked what it could check, and
        a green run means no rule in this pack failed — not that the system
        satisfies Article 50 in full.
        """
        return self.failed == 0


class Signature(BaseModel):
    """Detached Ed25519 signature over the canonical form of the report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm: str = "Ed25519"
    canonicalizer: str
    """Exact canonicaliser and version, e.g. ``rfc8785==0.1.4``. Without it a
    verifier years later cannot know which bytes were signed."""

    public_key: str
    """Base64 of the raw public key. Travels with the report so a reader can
    check the signature without a side channel — it proves integrity, and
    whether that key is *trusted* is a question the reader answers elsewhere."""

    value: str
    """Base64 of the signature over the canonical report without this block."""


class Report(BaseModel):
    """A complete, self-describing conformance report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = REPORT_SCHEMA_VERSION
    target: str
    rulepack: dict[str, str]

    applicability: dict[str, bool] | None = None
    """The target's declaration of which Article 50 obligations bind it.

    Absent when nobody declared anything, which keeps a report from a plain
    config byte-identical to what it was before this field existed.

    Present, it is covered by the signature — and that is the point. A report
    that skipped the deep fake rule now says, over the operator's own key, that
    they declared no deep fakes. The scope of a green run stops being an
    assumption the reader has to supply and becomes a claim someone signed.
    """

    run: RunMetadata
    findings: list[Finding]
    summary: Summary
    signature: Signature | None = None

    def unsigned(self) -> Report:
        """This report without its signature block.

        The signature covers everything else, so verification has to reconstruct
        exactly this object.
        """
        return self.model_copy(update={"signature": None})

    def to_canonical_dict(self) -> dict[str, Any]:
        """The dict that gets canonicalised and signed."""
        return self.unsigned().model_dump(mode="json", exclude_none=True)


def _summarise(findings: list[Finding]) -> Summary:
    counts = dict.fromkeys(Result, 0)
    for finding in findings:
        counts[finding.result] += 1
    return Summary(
        passed=counts[Result.PASS],
        failed=counts[Result.FAIL],
        warned=counts[Result.WARN],
        skipped=counts[Result.SKIP],
    )


def build_report(
    *,
    target: str,
    rulepack: Rulepack,
    findings: list[Finding],
    timestamp: str | None = None,
    applicability: Applicability | None = None,
    run: RunMetadata | None = None,
) -> Report:
    """Assemble a report from a completed run.

    Args:
        target: The configured target name.
        rulepack: The rulepack the findings were produced against.
        findings: Findings in evaluator order — already stable.
        timestamp: ISO-8601 UTC. Injectable so tests can pin it; defaults to
            now, because an unsigned artefact without a time is not evidence.
        run: The whole run block, when every field of it has to be pinned.
            Overrides ``timestamp``. The determinism gate needs this: the
            interpreter version and the platform are recorded on purpose, so two
            honest runs of the same evidence on a Mac and on a Linux runner
            legitimately differ in bytes, and a golden file that embedded either
            would fail everywhere except the machine that wrote it.
        applicability: The scope the operator declared. Recorded verbatim, and
            omitted entirely when empty — an empty declaration and no
            declaration are the same statement, and writing one out would
            suggest a claim nobody made.
    """
    declared = (
        {o.value: v for o, v in sorted(applicability.root.items())}
        if applicability is not None and applicability.root
        else None
    )
    return Report(
        target=target,
        applicability=declared,
        rulepack={
            "id": rulepack.rulepack,
            "version": rulepack.version,
            "license": rulepack.license,
            # The findings quote title, article and guideline_ref verbatim from
            # CC-BY material, so the credit line has to travel with them. A
            # report that carries the text but not the attribution does not
            # discharge the licence.
            "attribution": " ".join(rulepack.attribution.split()),
        },
        run=run
        or RunMetadata(
            timestamp=timestamp or datetime.now(UTC).isoformat(timespec="seconds"),
            markproof_version=__version__,
            python_version=platform.python_version(),
            platform=platform.system().lower(),
        ),
        findings=findings,
        summary=_summarise(findings),
    )
