# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Markdown summary — the report as it appears in a CI job.

Written for someone who opens a failed pipeline and wants to know, in five
seconds, what broke and where to look. Failures come first and carry their
citation; passing rules are collapsed into a line, because nobody reads a wall
of green.

Pure string building: no system dependencies, so this path works on any runner.
That is deliberate — the PDF is optional, this is not.
"""

from __future__ import annotations

from markproof.report.model import Report
from markproof.rules.engine import Finding, Result

__all__ = ["render_summary"]

#: Emoji read faster than words in a job log, and GitHub renders them everywhere.
_ICONS = {
    Result.PASS: "✅",
    Result.FAIL: "❌",
    Result.WARN: "⚠️",
    Result.SKIP: "⏭️",
}

#: Order findings by how much they demand attention, then by rule id.
_PRIORITY = {Result.FAIL: 0, Result.WARN: 1, Result.SKIP: 2, Result.PASS: 3}


def _escape(text: str) -> str:
    """Keep a message from breaking the table it sits in."""
    return text.replace("|", "\\|").replace("\n", " ")


def _verdict_line(report: Report) -> str:
    summary = report.summary
    if summary.failed:
        return (
            f"**{summary.failed} of {summary.total} checks failed.** "
            "This build does not satisfy the rules in the pack."
        )
    if summary.warned:
        return (
            f"**No failures, {summary.warned} finding(s) need a human.** "
            "Warnings mark what the tool could not decide on its own."
        )
    if summary.skipped and not summary.passed:
        return "**Nothing was checked.** Every rule was skipped — see the reasons below."
    return f"**All {summary.passed} applicable checks passed.**"


#: Printed wherever a marking rule passes. Not a disclaimer in a footer: the risk
#: is a reader concluding from "MPF-T-001 PASS" that Article 50(2) is satisfied,
#: so the qualification has to sit where that conclusion is drawn.
MARKING_LIMB_NOTE = (
    "**Article 50(2) has two limbs.** The marking checks above measure whether the "
    "mark arrived, against your own configuration. They do not measure whether a "
    "third party can detect it — that is a property of the ecosystem, not of your "
    "endpoint, and no probe run against your system can establish it. A passing "
    "marking check is not, on its own, Article 50(2) compliance."
)


def _marking_note(report: Report) -> list[str]:
    """The Article 50(2) qualification, when a marking rule actually passed.

    Only on a pass. A reader whose marking check failed or skipped is not at risk
    of over-reading it, and a note that appears unconditionally is one more line
    people learn to skip — the same failure as a warning that fires for every
    target.
    """
    passed = [
        f
        for f in report.findings
        if f.result is Result.PASS and f.obligation is not None and f.obligation.is_marking
    ]
    if not passed:
        return []
    return ["", MARKING_LIMB_NOTE, ""]


def _join(names: list[str]) -> str:
    """Backtick the names and join them so the sentence reads as English."""
    quoted = [f"`{n}`" for n in names]
    if len(quoted) <= 1:
        return "".join(quoted)
    return f"{', '.join(quoted[:-1])} or {quoted[-1]}"


def _scope_block(report: Report) -> list[str]:
    """What the operator declared out of scope, and what they claimed applies.

    Printed next to the verdict rather than in a footnote. A reader deciding how
    much a green run is worth needs the scope in the same glance as the result —
    put it at the bottom and the number above it reads as broader than it is.
    """
    declared = report.applicability
    if not declared:
        return []

    out = sorted(k for k, v in declared.items() if not v)
    inside = sorted(k for k, v in declared.items() if v)

    sentences: list[str] = []
    if out:
        sentences.append(
            f"The target declares no {_join(out)} "
            f"obligation{'s' if len(out) > 1 else ''}, so the rules serving "
            f"{'them' if len(out) > 1 else 'it'} were skipped rather than measured."
        )
    if inside:
        sentences.append(
            f"It declares that {_join(inside)} {'apply' if len(inside) > 1 else 'applies'}."
        )
    sentences.append(
        "This is the operator's own statement, recorded here and covered by the signature."
    )
    return [f"**Declared scope.** {' '.join(sentences)}", ""]


def _findings_table(findings: list[Finding]) -> list[str]:
    lines = [
        "| | Rule | Probe | Result |",
        "|---|---|---|---|",
    ]
    for finding in sorted(findings, key=lambda f: (_PRIORITY[f.result], f.rule_id)):
        lines.append(
            f"| {_ICONS[finding.result]} | `{finding.rule_id}` | {finding.probe_id} "
            f"| {_escape(finding.message)} |"
        )
    return lines


def _detail_blocks(findings: list[Finding]) -> list[str]:
    """One block per finding that needs acting on, with its citation."""
    blocks: list[str] = []
    needing_attention = [f for f in findings if f.result in (Result.FAIL, Result.WARN)]
    for finding in sorted(needing_attention, key=lambda f: (_PRIORITY[f.result], f.rule_id)):
        blocks.append("")
        blocks.append(f"### {_ICONS[finding.result]} {finding.rule_id} — {finding.title}")
        blocks.append("")
        blocks.append(f"{finding.message}")
        blocks.append("")
        citation = finding.article
        if finding.guideline_ref:
            citation += f" · {finding.guideline_ref}"
        blocks.append(f"- **Obligation:** {citation}")
        blocks.append(f"- **Probe:** `{finding.probe_id}`")
        for key, value in sorted(finding.detail.items()):
            if key == "outcome":
                continue
            rendered = ", ".join(str(v) for v in value) if isinstance(value, list) else value
            blocks.append(f"- **{key.replace('_', ' ')}:** {rendered}")
        if finding.evidence_sha256:
            digests = ", ".join(f"`{d[:12]}…`" for d in finding.evidence_sha256)
            blocks.append(f"- **Evidence:** {digests}")
    return blocks


def render_summary(report: Report) -> str:
    """Render the report as GitHub-flavoured Markdown."""
    summary = report.summary
    lines = [
        f"## markproof — {report.target}",
        "",
        _verdict_line(report),
        "",
        f"`{report.rulepack['id']}` v{report.rulepack['version']} · "
        f"{summary.passed} passed · {summary.failed} failed · "
        f"{summary.warned} warned · {summary.skipped} skipped",
        "",
    ]
    lines.extend(_scope_block(report))

    if report.findings:
        lines.extend(_findings_table(report.findings))
        lines.extend(_detail_blocks(report.findings))
    else:
        lines.append("_No rule in this pack applied to the configured probes._")

    lines.extend(_marking_note(report))
    lines.extend(["", "---", ""])

    if report.signature is not None:
        lines.append(
            f"Signed with {report.signature.algorithm}, canonicalised by "
            f"`{report.signature.canonicalizer}`. Verify with "
            "`markproof verify-report report.json --key public.pem`."
        )
    else:
        lines.append(
            "_Unsigned report._ Set `MARKPROOF_SIGNING_KEY` to produce evidence a "
            "third party can verify."
        )

    attribution = report.rulepack.get("attribution")
    if attribution:
        # The findings quote the guidelines; the credit line goes with them.
        lines.extend(["", f"_{attribution}_"])

    lines.extend(
        [
            "",
            f"Checked at {report.run.timestamp} · markproof {report.run.markproof_version}",
            "",
            "This is a technical conformance test, not legal advice, and a passing "
            "report attests only that the listed checks passed at that moment.",
        ]
    )
    return "\n".join(lines) + "\n"
