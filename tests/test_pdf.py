# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""PDF output — the optional, human-readable enclosure.

Two things are worth testing here and one thing is not. Worth testing: that the
renderers produce a real PDF from a report object they have never seen (the
adapter is deliberately duck-typed, so it can silently rot), and that the
weasyprint path fails loudly and helpfully instead of falling back to reportlab.
Not worth testing: what the page looks like. Pixel assertions on a layout are a
maintenance tax that catches nothing a human would call a bug.

The report model is developed in parallel, so these tests drive the renderers
with a ``SimpleNamespace`` shaped like the documented protocol — which is also
the closest thing to a specification the protocol has. The findings, by
contrast, are the real :class:`markproof.rules.engine.Finding`: those field
names are fixed, so one test pins the adapter against the actual class rather
than against a fake that could drift with it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from markproof.report import pdf_reportlab, pdf_weasy
from markproof.report.model import build_report
from markproof.rules.engine import Finding, Result
from markproof.rules.schema import Rulepack

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return True


def _weasyprint_available() -> bool:
    # OSError, not just ImportError: the wheel installs fine while ctypes fails
    # to find Pango or cairo, which is the usual state of a bare CI image.
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


needs_reportlab = pytest.mark.skipif(
    not _reportlab_available(), reason="needs the [pdf] extra (reportlab)"
)
needs_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(), reason="needs the [pdf-html] extra and Pango/cairo"
)


def _hide_module(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make ``import <name>`` fail, even where the package is installed.

    Dropping the cached submodules matters: with ``reportlab.lib.colors`` still
    in ``sys.modules`` the import machinery answers from the cache and never
    consults the poisoned parent entry, so the test would pass for the wrong
    reason on a machine that has the extra.
    """
    for cached in [m for m in list(sys.modules) if m == name or m.startswith(f"{name}.")]:
        monkeypatch.delitem(sys.modules, cached, raising=False)
    monkeypatch.setitem(sys.modules, name, None)


def _finding(
    rule_id: str = "MPF-D-001",
    result: Result = Result.FAIL,
    **overrides: Any,
) -> Finding:
    """A real engine finding — the one part of the protocol that is already fixed."""
    fields: dict[str, Any] = {
        "rule_id": rule_id,
        "title": "Chatbot discloses that it is an AI",
        "article": "Art. 50(1)",
        "guideline_ref": "Guidelines 20.07.2026, Rn. 42",
        "probe_id": "chat-de",
        "result": result,
        "message": "no AI disclosure found in the responses in scope",
        "detail": {"outcome": "not_disclosed", "lang": "de", "inspected_prompts": ["opener"]},
        "evidence_sha256": (_HASH_A, _HASH_B),
    }
    fields.update(overrides)
    return Finding(**fields)


def _report(findings: list[Any] | None = None, **overrides: Any) -> SimpleNamespace:
    """A stand-in for ``markproof.report.model.Report``.

    Shaped after the protocol documented in ``pdf_reportlab``. When the real
    model lands, the renderers should need no change — and if they do, this is
    the fake that has to be updated to say so.
    """
    fields: dict[str, Any] = {
        "target_name": "acme-support-bot",
        "rulepack_id": "eu-ai-act-art50",
        "rulepack_version": "2026.07",
        "generated_at": "2026-08-31T09:15:00+00:00",
        "markproof_version": "0.1.0.dev0",
        "git_sha": "0123456789abcdef",
        "attribution": "Contains information from the European Commission, CC BY 4.0.",
        "signature": SimpleNamespace(
            algorithm="Ed25519",
            key_id="SHA256:2f0c…",
            canonicalizer="rfc8785==0.1.4",
        ),
        "findings": [_finding()] if findings is None else findings,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


# ---------------------------------------------------------------------------
# Adapter — runs without either extra
# ---------------------------------------------------------------------------


def test_view_reads_the_documented_protocol() -> None:
    view = pdf_reportlab.report_view(_report())

    assert view.target_name == "acme-support-bot"
    assert view.rulepack_label == "eu-ai-act-art50 2026.07"
    assert view.markproof_version == "0.1.0.dev0"
    assert view.signed is True
    assert ("Git commit", "0123456789abcdef") in view.provenance
    assert view.findings[0].result == "FAIL"
    assert view.findings[0].evidence_sha256 == (_HASH_A, _HASH_B)


def test_view_survives_a_report_that_has_almost_nothing() -> None:
    """A partial model must degrade to a thinner page, never to an exception."""
    view = pdf_reportlab.report_view(SimpleNamespace())

    assert view.target_name == "(unnamed target)"
    assert view.findings == ()
    assert view.signed is False
    assert view.blocking is False
    assert view.counts == {"FAIL": 0, "WARN": 0, "PASS": 0, "SKIP": 0}


def test_view_accepts_nested_and_mapping_shaped_reports() -> None:
    """The model may nest target/rulepack, or be a plain dict from JSON."""
    nested = SimpleNamespace(
        target=SimpleNamespace(name="nested-bot"),
        rulepack=SimpleNamespace(id="rp", version="1"),
    )
    assert pdf_reportlab.report_view(nested).target_name == "nested-bot"
    assert pdf_reportlab.report_view(nested).rulepack_label == "rp 1"

    as_dict = {"target_name": "dict-bot", "findings": [], "rulepack_id": "rp"}
    assert pdf_reportlab.report_view(as_dict).target_name == "dict-bot"


def test_view_counts_and_blocking_follow_the_exit_code_rule() -> None:
    """WARN and SKIP never block — the same rule the engine's exit code uses."""
    view = pdf_reportlab.report_view(
        _report(
            [
                _finding("MPF-D-001", Result.PASS),
                _finding("MPF-M-001", Result.WARN),
                _finding("MPF-T-001", Result.SKIP),
            ]
        )
    )
    assert view.blocking is False
    assert view.counts == {"FAIL": 0, "WARN": 1, "PASS": 1, "SKIP": 1}

    failing = pdf_reportlab.report_view(_report([_finding("MPF-M-001", Result.FAIL)]))
    assert failing.blocking is True
    assert len(failing.failures) == 1


def test_result_colours_are_semantic_and_distinct() -> None:
    """Four results, four colours, and never colour alone: the label is text."""
    palette = pdf_reportlab.RESULT_PALETTE
    assert set(palette) == {"PASS", "FAIL", "WARN", "SKIP"}
    assert len({ink for ink, _ in palette.values()}) == 4
    # An unknown label must not crash the layout; it renders neutral grey.
    unknown = pdf_reportlab.FindingView(
        rule_id="X",
        title="",
        article="",
        guideline_ref="",
        probe_id="",
        result="WOBBLE",
        message="",
    )
    assert unknown.palette == palette["SKIP"] or unknown.palette[0] == "#4b5563"


def test_view_reads_the_real_report_model(rulepack: Rulepack) -> None:
    """The duck-typed adapter against the actual ``Report``, not against a fake.

    This is the test that fails when the model and the renderers drift apart —
    the fake above cannot notice a renamed field, because it would be renamed in
    the fake too. Any failure here is fixed in ``report_view``'s lookup tuples,
    which are the entire adapter surface.
    """
    report = build_report(
        target="acme-support-bot",
        rulepack=rulepack,
        findings=[_finding("MPF-D-001", Result.FAIL)],
        timestamp="2026-08-31T09:15:00+00:00",
    )
    view = pdf_reportlab.report_view(report)

    assert view.target_name == "acme-support-bot"
    assert view.rulepack_label == "test-pack 1.0.0"
    assert view.generated_at == "2026-08-31T09:15:00+00:00"
    assert view.markproof_version == report.run.markproof_version
    assert view.markproof_version != "(unknown)"
    assert dict(view.provenance)["Python"] == report.run.python_version
    assert view.counts["FAIL"] == 1
    assert view.blocking is True
    assert view.signed is False  # build_report leaves signing to the signer


# ---------------------------------------------------------------------------
# reportlab — the portable default
# ---------------------------------------------------------------------------


@needs_reportlab
def test_renders_the_real_report_model(tmp_path: Path, rulepack: Rulepack) -> None:
    """End to end from ``build_report`` to a file on disk."""
    report = build_report(
        target="acme-support-bot",
        rulepack=rulepack,
        findings=[_finding("MPF-D-001", Result.FAIL), _finding("MPF-D-002", Result.PASS)],
        timestamp="2026-08-31T09:15:00+00:00",
    )
    out = tmp_path / "report.pdf"
    pdf_reportlab.render_pdf(report, out)

    assert out.read_bytes().startswith(b"%PDF")
    assert "test-pack 1.0.0" in pdf_weasy.render_html(report)


@needs_reportlab
def test_renders_a_real_pdf(tmp_path: Path) -> None:
    out = tmp_path / "report.pdf"
    pdf_reportlab.render_pdf(_report(), out)

    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 1500


@needs_reportlab
def test_creates_the_report_directory(tmp_path: Path) -> None:
    """``--report-dir`` may name a directory that does not exist yet."""
    out = tmp_path / "nested" / "dir" / "report.pdf"
    pdf_reportlab.render_pdf(_report(), out)
    assert out.is_file()


@needs_reportlab
def test_renders_every_result_kind(tmp_path: Path) -> None:
    out = tmp_path / "all-results.pdf"
    pdf_reportlab.render_pdf(
        _report(
            [
                _finding("MPF-D-001", Result.PASS),
                _finding("MPF-D-002", Result.FAIL),
                _finding("MPF-M-001", Result.WARN),
                _finding("MPF-T-001", Result.SKIP, guideline_ref=None, evidence_sha256=()),
            ]
        ),
        out,
    )
    assert out.read_bytes().startswith(b"%PDF")


@needs_reportlab
def test_renders_an_empty_and_a_bare_report(tmp_path: Path) -> None:
    """No findings, and a report missing every optional field, still render."""
    empty = tmp_path / "empty.pdf"
    pdf_reportlab.render_pdf(_report([]), empty)
    assert empty.read_bytes().startswith(b"%PDF")

    bare = tmp_path / "bare.pdf"
    pdf_reportlab.render_pdf(SimpleNamespace(findings=[_finding()]), bare)
    assert bare.read_bytes().startswith(b"%PDF")


@needs_reportlab
def test_long_text_wraps_instead_of_overflowing(tmp_path: Path) -> None:
    """Nothing is truncated: a clipped message loses evidence silently.

    A 3000-character message and a 400-character unbroken token are the two ways
    a table cell blows up — the first has to reflow across lines, the second has
    to be split mid-word rather than run off the page. Both are layout errors
    that reportlab raises on, so building the document at all is the assertion.
    """
    long_message = "Sehr langer Befund. " * 150
    unbroken = "x" * 400
    out = tmp_path / "long.pdf"
    pdf_reportlab.render_pdf(
        _report(
            [
                _finding("MPF-D-001", Result.FAIL, message=f"{long_message} {unbroken}"),
                _finding("MPF-M-001", Result.FAIL, detail={"assets": [unbroken]}),
            ]
        ),
        out,
    )
    assert out.read_bytes().startswith(b"%PDF")


@needs_reportlab
def test_markup_characters_in_findings_do_not_break_the_document(tmp_path: Path) -> None:
    """reportlab parses paragraph text as XML, so ``<`` and ``&`` must be escaped."""
    out = tmp_path / "markup.pdf"
    pdf_reportlab.render_pdf(
        _report(
            [
                _finding(
                    "MPF-D-001",
                    Result.FAIL,
                    title="A & B <not a tag>",
                    message="response contained <b>markup</b> & an ampersand",
                )
            ],
            target_name="<script>alert(1)</script>",
        ),
        out,
    )
    assert out.read_bytes().startswith(b"%PDF")


@pytest.mark.determinism
@needs_reportlab
def test_same_findings_render_the_same_bytes(tmp_path: Path) -> None:
    """Best effort only — see the reproducibility note in ``pdf_reportlab``.

    ``invariant=1`` pins reportlab's creation timestamp and document id, so the
    same findings on the same reportlab version produce the same file. That
    guarantee does not survive a reportlab upgrade, and the PDF is not covered
    by the report signature: ``report.json`` remains the evidence.
    """
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    pdf_reportlab.render_pdf(_report(), first)
    pdf_reportlab.render_pdf(_report(), second)
    assert first.read_bytes() == second.read_bytes()


def test_missing_reportlab_explains_the_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the extra: one actionable line, not an ImportError from inside a table."""
    _hide_module(monkeypatch, "reportlab")
    out = tmp_path / "report.pdf"

    with pytest.raises(pdf_reportlab.ReportlabUnavailableError) as excinfo:
        pdf_reportlab.render_pdf(_report(), out)

    message = str(excinfo.value)
    assert "markproof[pdf]" in message
    assert "reportlab" in message
    assert not out.exists()


# ---------------------------------------------------------------------------
# weasyprint — optional HTML path, never a fallback
# ---------------------------------------------------------------------------


def test_html_carries_the_facts_a_reader_needs() -> None:
    """The template is testable without weasyprint, which is the point of splitting it."""
    html = pdf_weasy.render_html(_report())

    assert "acme-support-bot" in html
    assert "eu-ai-act-art50 2026.07" in html
    assert "0.1.0.dev0" in html
    assert "MPF-D-001" in html
    assert "Art. 50(1)" in html
    assert "Guidelines 20.07.2026, Rn. 42" in html
    assert _HASH_A in html and _HASH_B in html  # full hashes, never abbreviated
    assert "not legal advice" in html
    assert "Ed25519" in html
    assert "Contains information from the European Commission" in html
    # Semantic colours reach the stylesheet, one class per result label.
    for label, (ink, _wash) in pdf_reportlab.RESULT_PALETTE.items():
        assert f".r-{label}" in html
        assert ink in html
    # Self-contained: no remote stylesheet, font or image to fetch.
    assert "http://" not in html and "https://" not in html


def test_html_escapes_finding_text() -> None:
    html = pdf_weasy.render_html(
        _report([_finding("MPF-D-001", Result.FAIL, message="<script>alert(1)</script> & co")])
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_marks_an_unsigned_report_as_unsigned() -> None:
    html = pdf_weasy.render_html(_report(signature=None))
    assert "unsigned" in html


def test_missing_weasyprint_names_the_system_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pip cannot install Pango or cairo, so the message has to say so."""
    _hide_module(monkeypatch, "weasyprint")
    out = tmp_path / "report.pdf"

    with pytest.raises(pdf_weasy.WeasyPrintUnavailableError) as excinfo:
        pdf_weasy.render_pdf(_report(), out)

    message = str(excinfo.value)
    assert "markproof[pdf-html]" in message
    assert "pango" in message.lower()
    assert "cairo" in message.lower()
    assert "apt-get" in message


def test_missing_weasyprint_never_falls_back_to_reportlab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A silent fallback would file a different document than the one requested.

    The failure has to leave nothing behind — a half-written or substituted PDF
    in the report directory is worse than no PDF, because the pipeline would
    archive it as if it were the requested one.
    """
    _hide_module(monkeypatch, "weasyprint")
    out = tmp_path / "report.pdf"

    with pytest.raises(pdf_weasy.WeasyPrintUnavailableError) as excinfo:
        pdf_weasy.render_pdf(_report(), out)

    assert not out.exists()
    assert list(tmp_path.iterdir()) == []
    assert not isinstance(excinfo.value, pdf_reportlab.ReportlabUnavailableError)
    assert "does not fall back" in str(excinfo.value)


@needs_weasyprint
def test_weasyprint_renders_a_real_pdf(tmp_path: Path) -> None:
    out = tmp_path / "report.pdf"
    pdf_weasy.render_pdf(_report(), out)

    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 1500
