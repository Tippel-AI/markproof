# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Portable PDF renderer (extra ``[pdf]``) — reportlab, pure Python.

The default PDF path because it has zero system dependencies and therefore
works on any CI runner (Auflage A2). Imperative layout instead of HTML
templating is a deliberate trade: robustness over template beauty.

Contents: header (target, rulepack id and version, run timestamp, markproof
version), a result table (rule, result, probe, message), a detail block per FAIL
carrying the Article and Guidelines reference plus the evidence hashes, and a
closing section with the signature status and the scope disclaimer.
Corporate-neutral, printable, no third-party logos (Auflage A3).

Optional by construction
------------------------
Nothing in the critical path imports this module at import time, and reportlab
is imported lazily inside :func:`render_pdf`. A run without the ``[pdf]`` extra
still produces the signed JSON and the Markdown summary; asking for a PDF
without the extra raises :class:`ReportlabUnavailableError` with the install
line, and never a stack trace from deep inside reportlab.

Reproducibility
---------------
**Treat the PDF as not byte-reproducible.** reportlab stamps a creation time and
a document id into every file. This renderer passes ``invariant=1``, which
pins both to fixed values, so two runs over the same findings on the same
reportlab version do come out byte-identical — but that guarantee ends at the
next reportlab release, a different font metric, or a changed layout constant,
and the PDF is not covered by the report signature. **The Ed25519-signed
``report.json`` is the authoritative evidence; the PDF is its human-readable
enclosure.** Anything an auditor needs to rely on must be verified with
``markproof verify-report``, not read off the print-out.

Adapter contract
----------------
The report model lives in :mod:`markproof.report.model` and is developed
separately. This renderer therefore reads a small, explicitly documented
protocol rather than a concrete class, via :func:`report_view`. Every field is
looked up by name on the object *or* on a mapping of the same shape, and every
field except ``findings`` has a defined fallback, so an early or reordered model
degrades to a thinner page instead of an exception.

Expected on the report (all optional unless noted):

``target_name`` / ``target`` / ``target.name``
    Name of the system under test. Falls back to ``"(unnamed target)"``.
``rulepack_id`` / ``rulepack.id``, ``rulepack_version`` / ``rulepack.version``
    Rulepack identity, printed together in the header.
``rulepack_attribution`` / ``attribution`` / ``rulepack.attribution``
    CC-BY attribution line for the shipped rulepacks (Auflage H1). Printed
    verbatim in the closing section when present.
``run.timestamp`` / ``generated_at`` / ``started_at`` / ``timestamp``
    ``datetime`` or string. Rendered as text; no timezone maths is attempted.
``run.markproof_version`` / ``markproof_version`` / ``version``
    Version of the tool that produced the report.
``run.python_version``, ``run.platform``, ``schema_version``, ``git_sha``,
``ci`` / ``ci_system``, ``run_id``
    Optional provenance rows, printed only when present.
``findings``
    **Required in substance** — a sequence of
    :class:`markproof.rules.engine.Finding` (fields ``rule_id``, ``title``,
    ``article``, ``guideline_ref``, ``probe_id``, ``result``, ``message``,
    ``detail``, ``evidence_sha256``). Those field names are fixed by the engine
    and are read directly. A missing or empty sequence renders an explicit
    "no findings" page rather than failing.
``signature``
    ``None``/absent means unsigned. Otherwise read for ``algorithm``,
    ``key_id`` / ``public_key_fingerprint`` / ``key_fingerprint``,
    ``canonicalizer`` and ``created_at``. The renderer reports the *presence* of
    a signature block; it never claims the signature was verified — only
    ``markproof verify-report`` can say that.

If the model later renames a field, extend the tuples in :func:`report_view`;
that function is the whole adapter surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

__all__ = [
    "DISCLAIMER",
    "RESULT_ORDER",
    "RESULT_PALETTE",
    "TRADEMARK_NOTICE",
    "FindingView",
    "ReportView",
    "ReportlabUnavailableError",
    "render_pdf",
    "report_view",
]


class ReportlabUnavailableError(RuntimeError):
    """The ``[pdf]`` extra is not installed.

    Raised instead of an ``ImportError`` from three frames deep, so the CLI can
    print one actionable line. The PDF is an optional output: a run that cannot
    render it still produced the signed JSON.
    """


_INSTALL_HINT: Final = (
    "PDF output needs reportlab, which is not installed.\n"
    "  pip install 'markproof[pdf]'\n"
    "reportlab is pure Python and has no system dependencies, so this works on "
    "any runner. The signed report.json and the Markdown summary are produced "
    "without it — the PDF is an optional enclosure, not the evidence."
)

#: Result label -> (ink, background wash). Semantic, not decorative: green PASS,
#: red FAIL, amber WARN, grey SKIP. Colour is never the only carrier — the label
#: text is printed in every badge, so the table survives greyscale printing and
#: colour-blind readers.
RESULT_PALETTE: Final[dict[str, tuple[str, str]]] = {
    "PASS": ("#166534", "#e3f4e8"),
    "FAIL": ("#b3261e", "#fbe4e2"),
    "WARN": ("#8a5300", "#fdf1d8"),
    "SKIP": ("#4b5563", "#eceef1"),
}

#: Order for the counts strip: what blocks the pipeline reads first.
RESULT_ORDER: Final[tuple[str, ...]] = ("FAIL", "WARN", "PASS", "SKIP")

_UNKNOWN_PALETTE: Final[tuple[str, str]] = ("#4b5563", "#eceef1")

_INK: Final = "#111827"
_MUTED: Final = "#5b6470"
_RULE: Final = "#d5d9df"

#: Reproduced verbatim from ``docs/DISCLAIMER.md`` — part of the release
#: checklist, not decoration.
DISCLAIMER: Final = (
    "markproof performs technical conformance testing. It is not legal advice. "
    "It runs deterministic checks against an endpoint you operate and reports what it found. "
    "A green run is evidence, not a legal opinion; a red run is a hint about a technical fact, "
    "not a finding of infringement. Coverage is limited to the machine-verifiable parts of "
    "Article 50; obligations that cannot be decided deterministically are reported as WARN with "
    "their evidence, never as a guessed PASS. For a legal assessment, talk to a lawyer."
)

TRADEMARK_NOTICE: Final = (
    "markproof is not affiliated with, endorsed by, or sponsored by Google DeepMind (SynthID), "
    "Adobe / the Content Authenticity Initiative (C2PA), or the European Commission. "
    "All trademarks are the property of their respective owners."
)

_SIGNATURE_CAVEAT: Final = (
    "This page reports the presence of a signature block, not its validity. "
    "Verify the report itself with "
    "<font face='Courier'>markproof verify-report report.json --key public.pem</font>."
)

_MISSING: Final = object()


# ---------------------------------------------------------------------------
# Adapter: report object (or mapping) -> flat view
# ---------------------------------------------------------------------------


def _member(obj: Any, name: str) -> Any:
    """One lookup step, on a mapping or an object."""
    if isinstance(obj, Mapping):
        return obj.get(name, _MISSING)
    return getattr(obj, name, _MISSING)


def _lookup(obj: Any, *paths: str) -> Any:
    """First present, non-``None`` value among dotted ``paths``, else ``_MISSING``."""
    for path in paths:
        current: Any = obj
        for part in path.split("."):
            current = _member(current, part)
            if current is _MISSING or current is None:
                break
        if current is not _MISSING and current is not None:
            return current
    return _MISSING


def _text(value: Any) -> str:
    """Render a scalar for display: enums by value, everything else by ``str``."""
    if value is None or value is _MISSING:
        return ""
    inner = getattr(value, "value", None)
    if isinstance(inner, str):  # StrEnum such as engine.Result
        return inner
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(v) for v in value)
    if isinstance(value, Mapping):
        return ", ".join(f"{k}={_text(v)}" for k, v in sorted(value.items()))
    return str(value)


def _string(obj: Any, *paths: str, default: str = "") -> str:
    value = _lookup(obj, *paths)
    rendered = _text(value).strip()
    return rendered or default


@dataclass(frozen=True)
class FindingView:
    """One finding, flattened to strings for layout.

    Mirrors :class:`markproof.rules.engine.Finding`, whose field names are fixed.
    """

    rule_id: str
    title: str
    article: str
    guideline_ref: str
    probe_id: str
    result: str
    message: str
    detail: tuple[tuple[str, str], ...] = ()
    evidence_sha256: tuple[str, ...] = ()

    obligation: str = ""
    """Which Article 50 duty this finding serves, when the report records one.

    Defaulted, like everything else this module reads: it renders whatever shape
    it is handed, including reports written by a build that had no such field.
    """

    @property
    def palette(self) -> tuple[str, str]:
        """Ink and wash for this result; unknown labels stay neutral grey."""
        return RESULT_PALETTE.get(self.result, _UNKNOWN_PALETTE)


#: The qualification a passing marking rule needs, without its Markdown emphasis —
#: this page renders its own. Kept beside the summary's wording deliberately: the
#: two artefacts state the same limit, and a reader comparing them should find no
#: difference to interpret.
MARKING_LIMB_NOTE = (
    "The marking checks above measure whether the mark arrived, against your own "
    "configuration. They do not measure whether a third party can detect it — that "
    "is a property of the ecosystem, not of your endpoint, and no probe run against "
    "your system can establish it. A passing marking check is not, on its own, "
    "Article 50(2) compliance."
)


def _join_names(names: list[str]) -> str:
    """Join obligation names so the sentence reads as English."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"


def _declared_scope(report: Any) -> tuple[tuple[str, bool], ...]:
    """The applicability declaration, if the report carries one.

    Tolerant like every reader in this module: the PDF renders whatever shape it
    is handed, including reports written by an older build that had no such
    field.
    """
    declared = _lookup(report, "applicability")
    if not isinstance(declared, dict):
        return ()
    return tuple((str(k), bool(v)) for k, v in sorted(declared.items()))


@dataclass(frozen=True)
class ReportView:
    """Everything the page needs, already reduced to strings."""

    target_name: str
    rulepack_id: str
    rulepack_version: str
    generated_at: str
    markproof_version: str
    marking_passed: bool = False
    """Whether any Article 50(2) marking rule passed.

    Drives the two-limbs qualification. This page is what somebody hands an
    auditor, so a reader concluding "marking: PASS, therefore Article 50(2)
    satisfied" would do it here rather than anywhere else."""

    findings: tuple[FindingView, ...] = ()
    declared_scope: tuple[tuple[str, bool], ...] = ()
    """Obligations the target declared, and whether each was said to apply.

    Printed with the verdict rather than in a footnote. This page is the artefact
    somebody hands to an auditor, and a PASS whose scope is only discoverable in
    the JSON alongside it would read as broader than it is.
    """

    provenance: tuple[tuple[str, str], ...] = ()
    attribution: str = ""
    signed: bool = False
    signature_rows: tuple[tuple[str, str], ...] = ()

    @property
    def counts(self) -> dict[str, int]:
        """Findings per result label, including labels with a zero count."""
        counts = dict.fromkeys(RESULT_ORDER, 0)
        for finding in self.findings:
            counts[finding.result] = counts.get(finding.result, 0) + 1
        return counts

    @property
    def failures(self) -> tuple[FindingView, ...]:
        return tuple(f for f in self.findings if f.result == "FAIL")

    @property
    def blocking(self) -> bool:
        """Whether this report set the process exit code. WARN and SKIP never do."""
        return bool(self.failures)

    @property
    def rulepack_label(self) -> str:
        parts = [p for p in (self.rulepack_id, self.rulepack_version) if p]
        return " ".join(parts) or "(unknown rulepack)"


def _detail_rows(finding: Any) -> tuple[tuple[str, str], ...]:
    """``Finding.detail`` as sorted key/value strings.

    Sorted rather than insertion-ordered so two runs over the same findings lay
    out identically regardless of how the dict was built.
    """
    detail = _lookup(finding, "detail")
    if not isinstance(detail, Mapping):
        return ()
    return tuple((str(key), _text(value)) for key, value in sorted(detail.items()))


def _hashes(finding: Any) -> tuple[str, ...]:
    value = _lookup(finding, "evidence_sha256")
    if value is _MISSING:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(_text(v) for v in value)
    return ()


def _finding_view(finding: Any) -> FindingView:
    """Adapt one engine ``Finding`` (or anything with its field names)."""
    return FindingView(
        rule_id=_string(finding, "rule_id", default="(unknown rule)"),
        title=_string(finding, "title"),
        article=_string(finding, "article"),
        obligation=_string(finding, "obligation"),
        guideline_ref=_string(finding, "guideline_ref"),
        probe_id=_string(finding, "probe_id"),
        result=_string(finding, "result", default="SKIP").upper(),
        message=_string(finding, "message"),
        detail=_detail_rows(finding),
        evidence_sha256=_hashes(finding),
    )


#: Optional provenance rows: (label, lookup paths). Printed only when present,
#: so a local run does not show three empty CI fields. The environment rows earn
#: their place in a filed report: "it passed here" is a weaker claim than "it
#: passed on this Python, on this platform, at this commit".
_PROVENANCE: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("Python", ("run.python_version", "python_version")),
    ("Platform", ("run.platform", "platform")),
    ("Git commit", ("git_sha", "commit", "run.git_sha", "run.commit")),
    ("CI system", ("ci", "ci_system", "run.ci", "run.ci_system")),
    ("Run id", ("run_id", "run.id", "run.run_id")),
    ("Report schema", ("schema_version", "report_schema_version")),
)

#: Signature block rows, same convention.
_SIGNATURE_FIELDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("Algorithm", ("algorithm", "alg")),
    ("Key", ("key_id", "public_key_fingerprint", "key_fingerprint", "public_key")),
    ("Canonicalisation", ("canonicalizer", "canonicalisation", "canonicalization")),
    ("Signed at", ("created_at", "signed_at", "timestamp")),
)


def report_view(report: Any) -> ReportView:
    """Flatten a report object (or mapping) into the view the renderers use.

    The entire adapter surface between this package's PDF renderers and
    :mod:`markproof.report.model`. Reads the documented protocol only, tolerates
    absent optional fields, and never raises on a partial model.
    """
    raw_findings = _lookup(report, "findings")
    findings: tuple[FindingView, ...] = ()
    if isinstance(raw_findings, Sequence) and not isinstance(raw_findings, (str, bytes)):
        # Engine order is already stable (rule id, probe id) — preserved, not re-sorted.
        findings = tuple(_finding_view(f) for f in raw_findings)

    provenance = tuple(
        (label, _string(report, *paths)) for label, paths in _PROVENANCE if _string(report, *paths)
    )

    signature = _lookup(report, "signature", "signature_block")
    signed = signature is not _MISSING
    signature_rows: tuple[tuple[str, str], ...] = ()
    if signed:
        signature_rows = tuple(
            (label, _string(signature, *paths))
            for label, paths in _SIGNATURE_FIELDS
            if _string(signature, *paths)
        )

    return ReportView(
        target_name=_string(
            report, "target_name", "target.name", "target", default="(unnamed target)"
        ),
        rulepack_id=_string(report, "rulepack_id", "rulepack.id", "rulepack"),
        rulepack_version=_string(report, "rulepack_version", "rulepack.version"),
        generated_at=_string(
            report,
            "run.timestamp",
            "generated_at",
            "started_at",
            "timestamp",
            "run.started_at",
            "run.generated_at",
            default="(no timestamp recorded)",
        ),
        markproof_version=_string(
            report,
            "run.markproof_version",
            "markproof_version",
            "tool_version",
            "version",
            default="(unknown)",
        ),
        findings=findings,
        marking_passed=any(
            f.result.upper() == "PASS" and "marking" in (f.obligation or "") for f in findings
        ),
        declared_scope=_declared_scope(report),
        provenance=provenance,
        attribution=_string(report, "rulepack_attribution", "attribution", "rulepack.attribution"),
        signed=signed,
        signature_rows=signature_rows,
    )


# ---------------------------------------------------------------------------
# reportlab
# ---------------------------------------------------------------------------


def _require_reportlab() -> Any:
    """Import reportlab lazily; raise one actionable error when it is absent."""
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ReportlabUnavailableError(_INSTALL_HINT) from exc

    return SimpleNamespace(
        A4=A4,
        HexColor=HexColor,
        KeepTogether=KeepTogether,
        Paragraph=Paragraph,
        ParagraphStyle=ParagraphStyle,
        SimpleDocTemplate=SimpleDocTemplate,
        Spacer=Spacer,
        TA_CENTER=TA_CENTER,
        TA_LEFT=TA_LEFT,
        Table=Table,
        TableStyle=TableStyle,
        mm=mm,
    )


_XML_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
)


def _esc(text: str) -> str:
    """Escape for reportlab's mini-markup, which parses paragraph text as XML."""
    for needle, replacement in _XML_ESCAPES:
        text = text.replace(needle, replacement)
    return text


def _styles(rl: Any) -> dict[str, Any]:
    """Paragraph styles.

    Everything wraps: platypus ``Paragraph`` cells reflow inside their column,
    and ``splitLongWords`` (reportlab's default) breaks a 64-character hash
    rather than letting it run off the page. No cell is ever truncated —
    a clipped message in a compliance report is a silent loss of evidence.
    """
    body = rl.ParagraphStyle(
        name="mp-body",
        fontName="Helvetica",
        fontSize=9,
        leading=12.5,
        textColor=rl.HexColor(_INK),
        alignment=rl.TA_LEFT,
        splitLongWords=1,
    )
    return {
        "title": rl.ParagraphStyle(
            name="mp-title", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=20
        ),
        "subtitle": rl.ParagraphStyle(
            name="mp-subtitle", parent=body, fontSize=9.5, textColor=rl.HexColor(_MUTED)
        ),
        "h2": rl.ParagraphStyle(
            name="mp-h2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=4,
            spaceAfter=6,
            # A heading stranded at the foot of a page above an empty gap reads
            # like the section is missing.
            keepWithNext=1,
        ),
        "body": body,
        "cell": rl.ParagraphStyle(name="mp-cell", parent=body, fontSize=8.5, leading=11),
        "cell-strong": rl.ParagraphStyle(
            name="mp-cell-strong", parent=body, fontName="Helvetica-Bold", fontSize=8.5, leading=11
        ),
        "cell-muted": rl.ParagraphStyle(
            name="mp-cell-muted",
            parent=body,
            fontSize=7.6,
            leading=9.5,
            textColor=rl.HexColor(_MUTED),
        ),
        "mono": rl.ParagraphStyle(
            name="mp-mono", parent=body, fontName="Courier", fontSize=7.4, leading=9.6
        ),
        "small": rl.ParagraphStyle(
            name="mp-small", parent=body, fontSize=7.6, leading=10, textColor=rl.HexColor(_MUTED)
        ),
    }


def _badge_style(rl: Any, styles: dict[str, Any], result: str, *, centred: bool = False) -> Any:
    """Bold, result-coloured text for a table badge.

    Alignment belongs to the paragraph style, not to the table: a table ``ALIGN``
    command positions a cell's content only when that content is a string, and
    silently does nothing to a ``Paragraph``.
    """
    ink = RESULT_PALETTE.get(result, _UNKNOWN_PALETTE)[0]
    return rl.ParagraphStyle(
        name=f"mp-badge-{result}{'-c' if centred else ''}",
        parent=styles["cell"],
        fontName="Helvetica-Bold",
        textColor=rl.HexColor(ink),
        alignment=rl.TA_CENTER if centred else rl.TA_LEFT,
    )


def _meta_table(
    rl: Any, styles: dict[str, Any], rows: Sequence[tuple[str, str]], width: float
) -> Any:
    """Two-column label/value table used for the header and the detail blocks."""
    data = [
        [
            rl.Paragraph(_esc(label), styles["cell-strong"]),
            rl.Paragraph(_esc(value) if value else "—", styles["cell"]),
        ]
        for label, value in rows
    ]
    table = rl.Table(data, colWidths=[0.24 * width, 0.76 * width], hAlign="LEFT")
    table.setStyle(
        rl.TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _counts_strip(rl: Any, styles: dict[str, Any], view: ReportView, width: float) -> Any:
    """One coloured cell per result label, in FAIL-first order."""
    counts = view.counts
    cells = []
    for label in RESULT_ORDER:
        cells.append(
            rl.Paragraph(
                f"<b>{counts.get(label, 0)}</b> {_esc(label)}",
                _badge_style(rl, styles, label, centred=True),
            )
        )
    table = rl.Table([cells], colWidths=[width / len(RESULT_ORDER)] * len(RESULT_ORDER))
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, rl.HexColor(_RULE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, rl.HexColor(_RULE)),
    ]
    for index, label in enumerate(RESULT_ORDER):
        wash = RESULT_PALETTE.get(label, _UNKNOWN_PALETTE)[1]
        commands.append(("BACKGROUND", (index, 0), (index, 0), rl.HexColor(wash)))
    table.setStyle(rl.TableStyle(commands))
    return table


def _findings_table(rl: Any, styles: dict[str, Any], view: ReportView, width: float) -> Any:
    """Rule / result / probe / message, one row per finding, header repeated."""
    header = [
        rl.Paragraph("Rule", styles["cell-strong"]),
        rl.Paragraph("Result", styles["cell-strong"]),
        rl.Paragraph("Probe", styles["cell-strong"]),
        rl.Paragraph("Message", styles["cell-strong"]),
    ]
    data = [header]
    for finding in view.findings:
        rule_cell = f"<b>{_esc(finding.rule_id)}</b>"
        if finding.title:
            rule_cell += f"<br/><font size='7.6' color='{_MUTED}'>{_esc(finding.title)}</font>"
        data.append(
            [
                rl.Paragraph(rule_cell, styles["cell"]),
                rl.Paragraph(_esc(finding.result), _badge_style(rl, styles, finding.result)),
                rl.Paragraph(_esc(finding.probe_id), styles["cell"]),
                rl.Paragraph(_esc(finding.message), styles["cell"]),
            ]
        )

    table = rl.Table(
        data,
        colWidths=[0.22 * width, 0.10 * width, 0.17 * width, 0.51 * width],
        repeatRows=1,
    )
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, 0), rl.HexColor("#f2f4f6")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, rl.HexColor("#9aa3ad")),
        ("BOX", (0, 0), (-1, -1), 0.5, rl.HexColor(_RULE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, rl.HexColor(_RULE)),
    ]
    for index, finding in enumerate(view.findings, start=1):
        commands.append(
            ("BACKGROUND", (1, index), (1, index), rl.HexColor(finding.palette[1])),
        )
    table.setStyle(rl.TableStyle(commands))
    return table


def _failure_block(rl: Any, styles: dict[str, Any], finding: FindingView, width: float) -> Any:
    """Everything a reader needs to act on one FAIL, kept on a single page."""
    ink, wash = finding.palette
    heading = rl.Table(
        [
            [
                rl.Paragraph(
                    f"<b>FAIL &nbsp;·&nbsp; {_esc(finding.rule_id)}</b> "
                    f"&nbsp; {_esc(finding.title)}",
                    rl.ParagraphStyle(
                        name=f"mp-fail-head-{finding.rule_id}",
                        parent=styles["cell"],
                        fontSize=9.5,
                        leading=12,
                        textColor=rl.HexColor(ink),
                    ),
                )
            ]
        ],
        colWidths=[width],
    )
    heading.setStyle(
        rl.TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), rl.HexColor(wash)),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, rl.HexColor(ink)),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    rows: list[tuple[str, str]] = [
        ("Article", finding.article),
        ("Guidelines ref.", finding.guideline_ref),
        ("Probe", finding.probe_id),
        ("Message", finding.message),
    ]
    rows.extend((f"detail · {key}", value) for key, value in finding.detail)

    parts: list[Any] = [heading, rl.Spacer(1, 5), _meta_table(rl, styles, rows, width)]

    if finding.evidence_sha256:
        parts.append(rl.Spacer(1, 4))
        # One hash per line, Courier, and never abbreviated: a shortened hash is
        # not a hash. Long tokens wrap inside the cell rather than overflow.
        hashes = "<br/>".join(_esc(h) for h in finding.evidence_sha256)
        evidence = rl.Table(
            [
                [
                    rl.Paragraph("Evidence SHA-256", styles["cell-strong"]),
                    rl.Paragraph(hashes, styles["mono"]),
                ]
            ],
            colWidths=[0.24 * width, 0.76 * width],
            hAlign="LEFT",
        )
        evidence.setStyle(
            rl.TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        parts.append(evidence)

    parts.append(rl.Spacer(1, 12))
    return rl.KeepTogether(parts)


def _draw_furniture(canvas: Any, doc: Any, note: str) -> None:
    """Footer on every page: scope note left, page number right.

    The "not legal advice" line rides on every page because pages get separated
    from each other the moment someone prints the report.
    """
    from reportlab.lib.colors import HexColor  # reportlab is loaded by now

    canvas.saveState()
    canvas.setStrokeColor(HexColor(_RULE))
    canvas.setLineWidth(0.5)
    y = doc.bottomMargin - 14
    canvas.line(doc.leftMargin, y + 9, doc.leftMargin + doc.width, y + 9)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(HexColor(_MUTED))
    canvas.drawString(doc.leftMargin, y, note)
    canvas.drawRightString(doc.leftMargin + doc.width, y, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _story(rl: Any, view: ReportView, width: float) -> list[Any]:
    """The flowable sequence, top to bottom."""
    styles = _styles(rl)
    story: list[Any] = [
        rl.Paragraph("EU AI Act Article 50 — conformance report", styles["title"]),
        rl.Paragraph(
            f"markproof {_esc(view.markproof_version)} &nbsp;·&nbsp; "
            f"{_esc(view.target_name)} &nbsp;·&nbsp; {_esc(view.generated_at)}",
            styles["subtitle"],
        ),
        rl.Spacer(1, 14),
    ]

    meta: list[tuple[str, str]] = [
        ("Target", view.target_name),
        ("Rulepack", view.rulepack_label),
        ("Run at", view.generated_at),
        ("markproof version", view.markproof_version),
    ]
    meta.extend(view.provenance)
    story.append(_meta_table(rl, styles, meta, width))
    story.append(rl.Spacer(1, 14))

    verdict = "FAIL" if view.blocking else "PASS"
    blocking = len(view.failures)
    verdict_note = (
        f"{blocking} blocking finding{'s' if blocking != 1 else ''} — CI exit code 1"
        if view.blocking
        else "no blocking findings — CI exit code 0. WARN and SKIP never set the exit code."
    )
    story.append(
        rl.Paragraph(
            f"<font color='{RESULT_PALETTE[verdict][0]}'><b>Overall: {verdict}</b></font> "
            f"&nbsp;·&nbsp; {_esc(verdict_note)}",
            styles["body"],
        )
    )
    story.append(rl.Spacer(1, 8))
    story.append(_counts_strip(rl, styles, view, width))

    if view.declared_scope:
        out = [name for name, applies in view.declared_scope if not applies]
        inside = [name for name, applies in view.declared_scope if applies]
        sentences = []
        if out:
            sentences.append(
                f"The target declares no {_join_names(out)} "
                f"obligation{'s' if len(out) > 1 else ''}, so the rules serving "
                f"{'them' if len(out) > 1 else 'it'} were skipped rather than measured."
            )
        if inside:
            sentences.append(
                f"It declares that {_join_names(inside)} "
                f"{'apply' if len(inside) > 1 else 'applies'}."
            )
        sentences.append(
            "This is the operator's own statement, and it is covered by the signature."
        )
        story.append(rl.Spacer(1, 10))
        story.append(
            rl.Paragraph(
                f"<b>Declared scope.</b> {_esc(' '.join(sentences))}",
                styles["body"],
            )
        )

    if view.marking_passed:
        story.append(rl.Spacer(1, 10))
        story.append(
            rl.Paragraph(
                "<b>Article 50(2) has two limbs.</b> " + _esc(MARKING_LIMB_NOTE),
                styles["body"],
            )
        )

    story.append(rl.Spacer(1, 18))

    story.append(rl.Paragraph("Findings", styles["h2"]))
    if view.findings:
        story.append(_findings_table(rl, styles, view, width))
    else:
        story.append(
            rl.Paragraph(
                "No findings. The run produced no rule evaluations — check that the rulepack "
                "applies to the configured probes.",
                styles["body"],
            )
        )
    story.append(rl.Spacer(1, 16))

    failures = view.failures
    if failures:
        heading = rl.Paragraph(f"Failure detail ({len(failures)})", styles["h2"])
        blocks = [_failure_block(rl, styles, finding, width) for finding in failures]
        # The heading travels with the first block explicitly. ``keepWithNext``
        # alone does not survive a following ``KeepTogether`` that has to move to
        # the next page, and a heading left behind above a blank half-page reads
        # like the failure detail is missing.
        story.append(rl.KeepTogether([heading, blocks[0]]))
        story.extend(blocks[1:])

    story.extend(_closing(rl, styles, view, width))
    return story


def _closing(rl: Any, styles: dict[str, Any], view: ReportView, width: float) -> list[Any]:
    """Signature status, attribution and the scope disclaimer."""
    parts: list[Any] = [rl.Paragraph("Signature and scope", styles["h2"])]

    if view.signed:
        status = "Signature block present."
        colour = RESULT_PALETTE["PASS"][0]
    else:
        status = "No signature block — this report is unsigned."
        colour = RESULT_PALETTE["WARN"][0]
    parts.append(
        rl.Paragraph(f"<font color='{colour}'><b>{_esc(status)}</b></font>", styles["body"])
    )
    parts.append(rl.Spacer(1, 5))
    if view.signature_rows:
        parts.append(_meta_table(rl, styles, view.signature_rows, width))
        parts.append(rl.Spacer(1, 5))
    parts.append(rl.Paragraph(_SIGNATURE_CAVEAT, styles["small"]))
    parts.append(rl.Spacer(1, 12))

    parts.append(rl.Paragraph(_esc(DISCLAIMER), styles["small"]))
    parts.append(rl.Spacer(1, 6))
    parts.append(rl.Paragraph(_esc(TRADEMARK_NOTICE), styles["small"]))
    if view.attribution:
        parts.append(rl.Spacer(1, 6))
        parts.append(rl.Paragraph(_esc(view.attribution), styles["small"]))
    parts.append(rl.Spacer(1, 6))
    parts.append(
        rl.Paragraph(
            "The Ed25519-signed report.json is the authoritative artefact; this PDF is its "
            "human-readable enclosure and is not itself signed.",
            styles["small"],
        )
    )
    return [rl.KeepTogether(parts)]


def render_pdf(report: Any, path: Path) -> None:
    """Render ``report`` to a PDF at ``path``.

    Args:
        report: Anything satisfying the protocol documented in this module's
            docstring — normally ``markproof.report.model.Report``. Read through
            :func:`report_view`, never mutated.
        path: Destination file. Parent directories are created.

    Raises:
        ReportlabUnavailableError: if the ``[pdf]`` extra is not installed. The
            caller should treat this as "no PDF", not as a failed run: the
            signed JSON and the Markdown summary do not depend on it.
    """
    rl = _require_reportlab()
    view = report_view(report)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = rl.SimpleDocTemplate(
        str(path),
        pagesize=rl.A4,
        leftMargin=18 * rl.mm,
        rightMargin=18 * rl.mm,
        topMargin=16 * rl.mm,
        bottomMargin=20 * rl.mm,
        title=f"markproof report — {view.target_name}",
        author="markproof",
        subject="EU AI Act Article 50 conformance report",
        creator=f"markproof {view.markproof_version}",
        # Pins reportlab's creation timestamp and document id. Best effort only:
        # see the reproducibility note in the module docstring.
        invariant=1,
    )
    footer = (
        f"markproof {view.markproof_version} · {view.target_name} · "
        "technical conformance test, not legal advice"
    )
    on_page = partial(_draw_furniture, note=footer)
    doc.build(_story(rl, view, doc.width), onFirstPage=on_page, onLaterPages=on_page)
