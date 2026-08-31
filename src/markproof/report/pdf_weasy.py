# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""HTML-templated PDF renderer (extra ``[pdf-html]``) — weasyprint.

Prettier output for people who want it, never in the critical path (Auflage A2).
weasyprint needs Pango, cairo and GdkPixbuf, which pip cannot install; the docs
name the ``apt`` line explicitly.

Never a fallback
----------------
When weasyprint or its system libraries are missing this renderer raises
:class:`WeasyPrintUnavailableError` with the install instructions. It does
**not** quietly hand the job to :mod:`markproof.report.pdf_reportlab`: the two
renderers produce visibly different documents, and silently shipping the other
one would mean an operator files a PDF that is not the one their pipeline
requested. Choosing the portable default is the caller's decision to make
explicitly — the portability test asserts exactly this behaviour.

Shared adapter
--------------
The report protocol is documented once, in
:mod:`markproof.report.pdf_reportlab`, and read here through its
:func:`~markproof.report.pdf_reportlab.report_view`. That module imports
reportlab lazily, so importing it costs nothing and pulls in no extra.

:func:`render_html` builds the document without touching weasyprint at all,
which keeps the template testable on a runner that has neither extra installed.

Reproducibility
---------------
As with the reportlab path, treat the PDF as **not byte-reproducible** — the
renderer stamps metadata, and output shifts with weasyprint, Pango and the fonts
present on the machine. The Ed25519-signed ``report.json`` is the authoritative
evidence; the PDF is its human-readable enclosure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from markproof.report.pdf_reportlab import (
    DISCLAIMER,
    RESULT_ORDER,
    RESULT_PALETTE,
    TRADEMARK_NOTICE,
    FindingView,
    ReportView,
    report_view,
)

__all__ = [
    "WeasyPrintUnavailableError",
    "render_html",
    "render_pdf",
]


class WeasyPrintUnavailableError(RuntimeError):
    """weasyprint, or one of its system libraries, could not be loaded.

    Deliberately distinct from the reportlab error so a caller can tell the two
    optional paths apart, and deliberately fatal: the alternative is producing a
    different document than the one that was asked for.
    """


_INSTALL_HINT: Final = (
    "HTML PDF output needs weasyprint, which could not be loaded ({reason}).\n"
    "\n"
    "  pip install 'markproof[pdf-html]'\n"
    "\n"
    "weasyprint also needs system libraries that pip cannot install — Pango, "
    "cairo and GdkPixbuf:\n"
    "  Debian/Ubuntu: apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 "
    "libcairo2 libgdk-pixbuf-2.0-0\n"
    "  macOS (Homebrew): brew install pango cairo gdk-pixbuf libffi\n"
    "\n"
    "markproof does not fall back to the reportlab renderer here, because that "
    "would silently produce a different document than the one requested. For a "
    "PDF with no system dependencies use the portable renderer explicitly "
    "(extra '[pdf]'); the signed report.json and the Markdown summary are "
    "produced either way."
)

_UNKNOWN_PALETTE: Final[tuple[str, str]] = ("#4b5563", "#eceef1")

_HTML_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def _esc(text: str) -> str:
    for needle, replacement in _HTML_ESCAPES:
        text = text.replace(needle, replacement)
    return text


def _palette(result: str) -> tuple[str, str]:
    return RESULT_PALETTE.get(result, _UNKNOWN_PALETTE)


def _result_css() -> str:
    """One rule per result label, generated from the shared palette.

    Semantic colour, defined in exactly one place: FAIL red, WARN amber, PASS
    green, SKIP grey. The label text is always printed as well, so greyscale
    printing loses nothing.
    """
    return "\n".join(
        f".r-{label} {{ color: {ink}; background: {wash}; }}"
        for label, (ink, wash) in RESULT_PALETTE.items()
    )


_CSS: Final = """
@page {{
  size: A4;
  margin: 16mm 18mm 20mm 18mm;
  @bottom-left {{
    content: "{footer}";
    font: 7pt Helvetica, sans-serif;
    color: #5b6470;
  }}
  @bottom-right {{
    content: "Page " counter(page);
    font: 7pt Helvetica, sans-serif;
    color: #5b6470;
  }}
}}
body {{ font: 9pt/1.4 Helvetica, Arial, sans-serif; color: #111827; }}
h1 {{ font-size: 17pt; margin: 0 0 2mm; }}
h2 {{ font-size: 11pt; margin: 7mm 0 2mm; }}
.subtitle {{ color: #5b6470; font-size: 9.5pt; margin: 0 0 6mm; }}
table {{ border-collapse: collapse; width: 100%; }}
/* Long messages and 64-character hashes wrap instead of being cut off. */
td, th {{
  vertical-align: top;
  overflow-wrap: anywhere;
  word-break: break-word;
}}
table.meta td {{ padding: 1mm 3mm 1mm 0; }}
table.meta td.k {{ width: 24%; font-weight: bold; }}
table.findings {{ border: 0.5pt solid #d5d9df; margin-top: 2mm; }}
table.findings th {{
  background: #f2f4f6;
  text-align: left;
  font-size: 8.5pt;
  padding: 1.6mm 2mm;
  border-bottom: 0.6pt solid #9aa3ad;
}}
table.findings td {{ font-size: 8.5pt; padding: 1.6mm 2mm; border: 0.4pt solid #d5d9df; }}
td.result {{ text-align: center; font-weight: bold; white-space: nowrap; }}
.counts td {{
  text-align: center;
  padding: 2.4mm 0;
  border: 0.5pt solid #d5d9df;
  font-size: 9pt;
}}
.rule-title {{ color: #5b6470; font-size: 7.6pt; }}
.fail {{ break-inside: avoid; margin-bottom: 5mm; }}
.fail .head {{ padding: 1.8mm 2.4mm; font-size: 9.5pt; }}
.hash {{ font-family: Courier, monospace; font-size: 7.4pt; }}
.small {{ color: #5b6470; font-size: 7.6pt; line-height: 1.35; }}
{results}
"""


def _meta_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<tr><td class="k">{_esc(k)}</td><td>{_esc(v) if v else "&mdash;"}</td></tr>'
        for k, v in rows
    )
    return f'<table class="meta">{body}</table>'


def _counts_html(view: ReportView) -> str:
    counts = view.counts
    cells = "".join(
        f'<td class="r-{label}"><b>{counts.get(label, 0)}</b> {label}</td>'
        for label in RESULT_ORDER
    )
    return f'<table class="counts"><tr>{cells}</tr></table>'


def _findings_html(view: ReportView) -> str:
    if not view.findings:
        return (
            "<p>No findings. The run produced no rule evaluations — check that the rulepack "
            "applies to the configured probes.</p>"
        )
    rows = []
    for finding in view.findings:
        title = (
            f'<br><span class="rule-title">{_esc(finding.title)}</span>' if finding.title else ""
        )
        rows.append(
            f"<tr>"
            f"<td><b>{_esc(finding.rule_id)}</b>{title}</td>"
            f'<td class="result r-{_esc(finding.result)}">{_esc(finding.result)}</td>'
            f"<td>{_esc(finding.probe_id)}</td>"
            f"<td>{_esc(finding.message)}</td>"
            f"</tr>"
        )
    head = "<tr><th>Rule</th><th>Result</th><th>Probe</th><th>Message</th></tr>"
    return f'<table class="findings">{head}{"".join(rows)}</table>'


def _failure_html(finding: FindingView) -> str:
    ink, wash = _palette(finding.result)
    rows: list[tuple[str, str]] = [
        ("Article", finding.article),
        ("Guidelines ref.", finding.guideline_ref),
        ("Probe", finding.probe_id),
        ("Message", finding.message),
    ]
    rows.extend((f"detail · {k}", v) for k, v in finding.detail)
    evidence = ""
    if finding.evidence_sha256:
        # Never abbreviated: a shortened hash is not a hash.
        hashes = "<br>".join(_esc(h) for h in finding.evidence_sha256)
        evidence = (
            '<table class="meta"><tr><td class="k">Evidence SHA-256</td>'
            f'<td class="hash">{hashes}</td></tr></table>'
        )
    return (
        f'<div class="fail">'
        f'<div class="head" style="color:{ink};background:{wash};'
        f'border-left:2.5pt solid {ink}">'
        f"<b>FAIL &middot; {_esc(finding.rule_id)}</b> &nbsp; {_esc(finding.title)}</div>"
        f"{_meta_table(rows)}{evidence}"
        f"</div>"
    )


def render_html(report: Any) -> str:
    """Build the HTML document for ``report``.

    Split out from :func:`render_pdf` on purpose: the template is then testable
    on a machine with neither weasyprint nor its system libraries, which is most
    CI runners.

    Args:
        report: Anything satisfying the protocol documented in
            :mod:`markproof.report.pdf_reportlab`.

    Returns:
        A complete, self-contained HTML document — no external stylesheet, no
        web font, no remote asset. weasyprint must never reach the network to
        render a compliance report.
    """
    view = report_view(report)

    meta: list[tuple[str, str]] = [
        ("Target", view.target_name),
        ("Rulepack", view.rulepack_label),
        ("Run at", view.generated_at),
        ("markproof version", view.markproof_version),
    ]
    meta.extend(view.provenance)

    verdict = "FAIL" if view.blocking else "PASS"
    blocking = len(view.failures)
    verdict_note = (
        f"{blocking} blocking finding{'s' if blocking != 1 else ''} — CI exit code 1"
        if view.blocking
        else "no blocking findings — CI exit code 0. WARN and SKIP never set the exit code."
    )

    failures = "".join(_failure_html(f) for f in view.failures)
    failure_section = (
        f"<h2>Failure detail ({len(view.failures)})</h2>{failures}" if view.failures else ""
    )

    if view.signed:
        signature_line = (
            f'<p style="color:{RESULT_PALETTE["PASS"][0]}"><b>Signature block present.</b></p>'
        )
    else:
        signature_line = (
            f'<p style="color:{RESULT_PALETTE["WARN"][0]}">'
            "<b>No signature block — this report is unsigned.</b></p>"
        )
    signature_meta = _meta_table(list(view.signature_rows)) if view.signature_rows else ""
    attribution = f'<p class="small">{_esc(view.attribution)}</p>' if view.attribution else ""

    footer = (
        f"markproof {view.markproof_version} · {view.target_name} · "
        "technical conformance test, not legal advice"
    )
    css = _CSS.format(footer=_esc(footer).replace('"', "'"), results=_result_css())

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>markproof report — {_esc(view.target_name)}</title>
<style>{css}</style>
</head><body>
<h1>EU AI Act Article 50 — conformance report</h1>
<p class="subtitle">markproof {_esc(view.markproof_version)} &middot;
{_esc(view.target_name)} &middot; {_esc(view.generated_at)}</p>
{_meta_table(meta)}
<p style="margin-top:6mm"><span style="color:{RESULT_PALETTE[verdict][0]}">
<b>Overall: {verdict}</b></span> &middot; {_esc(verdict_note)}</p>
{_counts_html(view)}
<h2>Findings</h2>
{_findings_html(view)}
{failure_section}
<h2>Signature and scope</h2>
{signature_line}
{signature_meta}
<p class="small">This page reports the presence of a signature block, not its validity.
Verify the report itself with
<span class="hash">markproof verify-report report.json --key public.pem</span>.</p>
<p class="small">{_esc(DISCLAIMER)}</p>
<p class="small">{_esc(TRADEMARK_NOTICE)}</p>
{attribution}
<p class="small">The Ed25519-signed report.json is the authoritative artefact; this PDF is its
human-readable enclosure and is not itself signed.</p>
</body></html>
"""


def _require_weasyprint() -> Any:
    """Import weasyprint, or raise one message that says how to fix it.

    ``ImportError`` covers the missing package; ``OSError`` covers the far more
    common case where the wheel is installed but ctypes cannot find Pango or
    cairo, which is what actually bites people on a bare CI image.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise WeasyPrintUnavailableError(_INSTALL_HINT.format(reason=exc)) from exc
    return HTML


def render_pdf(report: Any, path: Path) -> None:
    """Render ``report`` to a PDF at ``path`` via HTML and weasyprint.

    Same signature as :func:`markproof.report.pdf_reportlab.render_pdf`, so the
    caller picks a renderer and nothing else changes.

    Args:
        report: Anything satisfying the protocol documented in
            :mod:`markproof.report.pdf_reportlab`.
        path: Destination file. Parent directories are created.

    Raises:
        WeasyPrintUnavailableError: if weasyprint or its system libraries cannot
            be loaded. No file is written and no other renderer is substituted.
    """
    html_class = _require_weasyprint()
    document = render_html(report)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # base_url stays None: the document is self-contained, so there is nothing to
    # resolve and no way for it to pull in a local or remote asset.
    html_class(string=document).write_pdf(str(path))
