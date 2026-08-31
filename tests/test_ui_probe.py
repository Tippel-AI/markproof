# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""UI probe against the static demo widget.

The fixture is ``examples/demo-bot/widget.html``, loaded over ``file://`` (and
over a throwaway HTTP server where an HTTP status is the thing under test). It
is fully inline, so these tests need no network — only a browser.

Two of them carry the milestone. ``TestVisibilityNotTheDom`` proves the probe
reads what a person sees rather than what the document claims: the ``no`` and
``late`` variants both contain a perfectly good disclosure sentence in the DOM,
one behind ``display: none`` and one inside an inert ``<template>``, and neither
may reach the evidence. ``TestRuleD002`` runs the shipped rulepack over the
collected evidence, which is the first time MPF-D-002 produces a verdict instead
of sitting inert for want of a probe that can answer it.

Everything that needs a browser is marked ``ui`` and skipped when the extra or
the Chromium binaries are absent — skipped visibly, in the test report, which is
a different thing from the probe skipping a check at run time. The probe never
does that.
"""

from __future__ import annotations

import importlib
import importlib.util
import struct
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from markproof.checks.disclosure import PatternSet, load_pattern_set
from markproof.config import TargetConfig, UiProbeConfig
from markproof.probes import ui as ui_module
from markproof.probes.base import ProbeError, Role
from markproof.probes.ui import UiProbe
from markproof.rules.engine import Finding, Result, evaluate
from markproof.rules.schema import ProbeKind, Rulepack, load_rulepack

_REPO = Path(__file__).resolve().parent.parent
_PKG = _REPO / "src" / "markproof"
_WIDGET = _REPO / "examples" / "demo-bot" / "widget.html"

#: Sentences the widget puts in the DOM but never on screen. Read from the file
#: itself in the tests below, so a reworded fixture fails loudly instead of
#: quietly testing nothing.
_HIDDEN_DE = "Hinweis: Sie chatten gerade mit einer KI. Dieser Absatz ist per CSS ausgeblendet."
_LATE_DE = "Zur Information: Sie chatten gerade mit einer KI, nicht mit einem Menschen."

#: Long enough that the extraction, which happens a few milliseconds after the
#: load event, cannot race the widget's own mount timer.
_MOUNT_DELAY_MS = 1500


def _browser_available() -> bool:
    """Whether Playwright *and* a working Chromium are actually here.

    Starts and closes a browser rather than only checking that a file exists:
    a half-extracted download passes the file test and fails every test after
    it. Costs about a second, once, at collection time.
    """
    if importlib.util.find_spec("playwright") is None:
        return False
    try:
        api = importlib.import_module("playwright.sync_api")
        with api.sync_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                return False
            playwright.chromium.launch(headless=True).close()
            return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(
    not _browser_available(),
    reason="needs the [ui] extra and 'playwright install chromium'",
)


def _widget_url(**params: str | int) -> str:
    """A ``file://`` URL for the demo widget with query parameters."""
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{_WIDGET.as_uri()}?{query}" if query else _WIDGET.as_uri()


def _config(url: str, **kwargs: Any) -> UiProbeConfig:
    base: dict[str, Any] = {"id": "widget", "type": "ui", "url": url, "lang": "de"}
    base.update(kwargs)
    return UiProbeConfig(**base)


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Width and height straight out of the IHDR chunk."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


class _QuietHandler(SimpleHTTPRequestHandler):
    """Serves the demo directory without narrating it into the test output."""

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture(scope="module")
def widget_server() -> Iterator[str]:
    """A throwaway HTTP server over ``examples/demo-bot``.

    Only for the cases where an HTTP status is the point; everything else uses
    ``file://`` so the suite stays offline in the strictest sense.
    """
    handler = partial(_QuietHandler, directory=str(_WIDGET.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def shipped_rulepack() -> Rulepack:
    return load_rulepack(_PKG / "rulepacks" / "art50-eu-2026.07.yaml")


@pytest.fixture(scope="module")
def shipped_patterns() -> dict[str, PatternSet]:
    return {"disclosure.de-en.yaml": load_pattern_set(_PKG / "patterns" / "disclosure.de-en.yaml")}


@pytest.fixture(scope="module")
def d002_pack(shipped_rulepack: Rulepack) -> Rulepack:
    """The shipped rulepack narrowed to MPF-D-002.

    The rule and its pattern file are the real, shipped ones, so a reworded
    rule or a changed pattern still breaks these tests. Narrowing it keeps them
    from also breaking on rules that belong to other milestones and other
    people's work in progress — this file is about the UI probe.
    """
    rules = [r for r in shipped_rulepack.rules if r.id == "MPF-D-002"]
    assert rules, "MPF-D-002 is gone from the shipped rulepack"
    assert rules[0].applies_to == [ProbeKind.UI], "MPF-D-002 no longer targets the UI probe"
    return shipped_rulepack.model_copy(update={"rules": rules})


class TestOptionalDependency:
    """The extra is optional; failing because of it is not."""

    def test_missing_playwright_names_both_install_steps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The browser download trips people up, so the hint must mention it.

        ``pip install 'markproof[ui]'`` alone leaves you with a driver and no
        browser, and the error that follows is unhelpful. Both commands or the
        message has not done its job.
        """

        def boom(name: str) -> Any:
            raise ImportError(f"No module named {name!r}")

        monkeypatch.setattr(ui_module, "importlib", SimpleNamespace(import_module=boom))

        with pytest.raises(ProbeError) as excinfo:
            UiProbe(_config("https://example.invalid/chat")).collect()

        message = str(excinfo.value)
        assert "markproof[ui]" in message
        assert "playwright install chromium" in message

    def test_a_missing_extra_is_an_error_not_a_skip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A probe that cannot run must never look like a probe that passed."""

        def boom(name: str) -> Any:
            raise ImportError(f"No module named {name!r}")

        monkeypatch.setattr(ui_module, "importlib", SimpleNamespace(import_module=boom))

        with pytest.raises(ProbeError):
            UiProbe(_config("https://example.invalid/chat")).collect()


class TestConfig:
    """Config validation — no browser involved."""

    def test_viewport_defaults_are_pinned(self) -> None:
        config = _config("https://example.invalid/")
        assert (config.viewport.width, config.viewport.height) == (1280, 800)

    def test_probe_kind_is_ui(self) -> None:
        assert _config("https://example.invalid/").probe_kind is ProbeKind.UI

    def test_the_union_discriminates_on_type(self) -> None:
        """A ``type: ui`` block must land in UiProbeConfig, not be ignored."""
        target = TargetConfig.model_validate(
            {
                "name": "demo",
                "probes": [
                    {"id": "widget", "type": "ui", "url": "https://example.invalid/chat"},
                    {"id": "chat", "type": "http-chat", "url": "https://example.invalid/v1"},
                ],
            }
        )
        assert isinstance(target.probes[0], UiProbeConfig)
        assert target.probes[0].probe_kind is ProbeKind.UI

    def test_file_urls_are_accepted(self) -> None:
        """A build artefact on disk is a legitimate rendered target."""
        assert _config(_WIDGET.as_uri()).url.startswith("file://")

    @pytest.mark.parametrize(
        "url", ["ftp://example.invalid/x", "example.invalid", "./build/widget.html"]
    )
    def test_other_schemes_are_rejected(self, url: str) -> None:
        with pytest.raises(ValueError, match="file://"):
            _config(url)

    def test_unsupported_language_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            _config("https://example.invalid/", lang="fr")

    @pytest.mark.parametrize("value", ["#chat", 250, 0, None])
    def test_wait_for_accepts_a_selector_or_milliseconds(self, value: str | int | None) -> None:
        assert _config("https://example.invalid/", wait_for=value).wait_for == value

    @pytest.mark.parametrize("value", [-1, 60_001])
    def test_wait_for_rejects_impossible_delays(self, value: int) -> None:
        with pytest.raises(ValueError, match="between 0 and 60000"):
            _config("https://example.invalid/", wait_for=value)

    def test_wait_for_rejects_a_boolean(self) -> None:
        """``wait_for: true`` in YAML is a mistake, not a one-millisecond pause."""
        with pytest.raises(ValueError, match="not a boolean"):
            _config("https://example.invalid/", wait_for=True)

    def test_blank_selector_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be blank"):
            _config("https://example.invalid/", wait_for="   ")

    def test_unknown_keys_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            _config("https://example.invalid/", screenshot_full_page=True)


@needs_browser
@pytest.mark.ui
class TestInitialView:
    """What the probe records before anyone has typed."""

    def test_the_turn_carries_no_request_at_all(self) -> None:
        """The heart of it: an empty request list is what makes the turn first.

        ``position: before_first_user_message`` selects turns where no user
        message precedes the response. If the probe invented a request here,
        MPF-D-002 would find nothing to inspect and go on warning forever.
        """
        turn = UiProbe(_config(_widget_url(disclosure="yes"))).collect().turns[0]

        assert turn.request == []
        assert turn.is_first is True
        assert turn.response.role is Role.ASSISTANT

    def test_a_visible_disclosure_is_recorded(self) -> None:
        text = UiProbe(_config(_widget_url(disclosure="yes"))).collect().turns[0].response.content
        assert "Sie chatten gerade mit einer KI" in text

    def test_evidence_is_shaped_for_the_ui_rules(self) -> None:
        evidence = UiProbe(_config(_widget_url(disclosure="yes"))).collect()

        assert evidence.probe_kind is ProbeKind.UI
        assert evidence.lang == "de"
        assert len(evidence.turns) == 1
        assert evidence.turns[0].prompt_id == "ui-initial-view"

    def test_the_selector_scopes_the_text(self) -> None:
        """With a selector the page header stays out of the evidence."""
        whole = UiProbe(_config(_widget_url(disclosure="no"))).collect()
        widget = UiProbe(
            _config(_widget_url(disclosure="no"), chat_selector="#chat-widget")
        ).collect()

        assert "Statisches Testziel" in whole.turns[0].response.content
        assert "Statisches Testziel" not in widget.turns[0].response.content

    def test_english_widget_is_read_in_english(self) -> None:
        evidence = UiProbe(_config(_widget_url(disclosure="yes", lang="en"), lang="en")).collect()
        assert "chatting with an AI" in evidence.turns[0].response.content


@needs_browser
@pytest.mark.ui
class TestScreenshotEvidence:
    """The annex an auditor looks at."""

    def test_a_png_is_attached_with_a_matching_digest(self) -> None:
        """Without the image, 'the notice was missing' is an unbacked claim."""
        import hashlib

        turn = UiProbe(_config(_widget_url(disclosure="yes"))).collect().turns[0]

        assert len(turn.artifacts) == 1
        artifact = turn.artifacts[0]
        assert artifact.media_type == "image/png"
        assert artifact.data is not None
        assert artifact.data[:8] == b"\x89PNG\r\n\x1a\n"
        assert artifact.size_bytes == len(artifact.data)
        assert artifact.sha256 == hashlib.sha256(artifact.data).hexdigest()
        assert artifact.source_url is not None

    def test_the_screenshot_has_the_configured_viewport_size(self) -> None:
        """A pinned viewport is what makes two runs comparable at all."""
        config = _config(_widget_url(disclosure="yes"), viewport={"width": 900, "height": 600})
        artifact = UiProbe(config).collect().turns[0].artifacts[0]

        assert artifact.data is not None
        assert _png_dimensions(artifact.data) == (900, 600)

    def test_image_bytes_stay_out_of_the_serialised_evidence(self) -> None:
        """A screenshot is a few dozen kilobytes; evidence must stay diffable."""
        evidence = UiProbe(_config(_widget_url(disclosure="yes"))).collect()
        dumped = evidence.model_dump_json()

        assert '"data"' not in dumped
        assert "sha256" in dumped


@needs_browser
@pytest.mark.ui
class TestVisibilityNotTheDom:
    """A notice nobody can read is not a notice."""

    def test_a_display_none_disclosure_is_not_observed(self) -> None:
        """``disclosure=no`` hides a textbook disclosure behind CSS.

        It is in the document. It is in no rendering of the document. A probe
        reading innerHTML would hand this deployment a pass.
        """
        assert _HIDDEN_DE in _WIDGET.read_text(encoding="utf-8"), "fixture no longer arms the trap"

        text = (
            UiProbe(_config(_widget_url(disclosure="no"), chat_selector="#chat-widget"))
            .collect()
            .turns[0]
            .response.content
        )

        assert _HIDDEN_DE not in text
        assert "KI" not in text

    def test_a_templated_late_disclosure_is_not_observed(self) -> None:
        """``disclosure=late`` keeps the wording in an inert ``<template>``.

        It reaches the user only after they have sent a message, which is the
        precise failure Article 50(1) is about: right words, wrong moment.
        """
        assert _LATE_DE in _WIDGET.read_text(encoding="utf-8"), "fixture no longer arms the trap"

        text = (
            UiProbe(_config(_widget_url(disclosure="late"), chat_selector="#chat-widget"))
            .collect()
            .turns[0]
            .response.content
        )

        assert _LATE_DE not in text
        assert "KI" not in text

    def test_an_invisible_widget_is_reported_not_read(self) -> None:
        """Pointed at the hidden node itself, the probe refuses to pretend."""
        config = _config(
            _widget_url(disclosure="no"),
            chat_selector="#hidden-disclosure-de",
            timeout_seconds=5,
        )
        with pytest.raises(ProbeError, match="not visible"):
            UiProbe(config).collect()


@needs_browser
@pytest.mark.ui
class TestRuleD002:
    """MPF-D-002 stops being inert.

    Until this probe existed the rule applied to a probe kind nothing produced,
    so it never ran. These are the verdicts it now reaches.
    """

    @staticmethod
    def _finding(
        mode: str,
        rulepack: Rulepack,
        patterns: dict[str, PatternSet],
        *,
        lang: str = "de",
    ) -> Finding:
        url = _widget_url(disclosure=mode, lang=lang)
        evidence = UiProbe(_config(url, lang=lang, chat_selector="#chat-widget")).collect()
        findings = [f for f in evaluate(rulepack, [evidence], patterns) if f.rule_id == "MPF-D-002"]
        assert len(findings) == 1, "MPF-D-002 did not produce exactly one finding"
        return findings[0]

    def test_a_visible_notice_passes(
        self, d002_pack: Rulepack, shipped_patterns: dict[str, PatternSet]
    ) -> None:
        finding = self._finding("yes", d002_pack, shipped_patterns)

        assert finding.result is Result.PASS
        assert finding.detail["outcome"] == "disclosed"
        assert finding.evidence_sha256, "a passing finding must reference the text it rests on"

    def test_the_english_widget_passes_too(
        self, d002_pack: Rulepack, shipped_patterns: dict[str, PatternSet]
    ) -> None:
        finding = self._finding("yes", d002_pack, shipped_patterns, lang="en")
        assert finding.result is Result.PASS

    @pytest.mark.parametrize("mode", ["no", "late"])
    def test_an_unreadable_or_late_notice_warns(
        self, mode: str, d002_pack: Rulepack, shipped_patterns: dict[str, PatternSet]
    ) -> None:
        """Warn, not fail: the rule reports presence, prominence stays human work."""
        finding = self._finding(mode, d002_pack, shipped_patterns)

        assert finding.result is Result.WARN
        assert finding.detail["outcome"] == "not_disclosed"

    def test_the_rule_inspects_the_unprompted_turn(
        self, d002_pack: Rulepack, shipped_patterns: dict[str, PatternSet]
    ) -> None:
        """Proof the position selector actually engaged rather than defaulting."""
        finding = self._finding("yes", d002_pack, shipped_patterns)
        assert finding.detail["inspected_prompts"] == ["ui-initial-view"]


@needs_browser
@pytest.mark.ui
class TestWaiting:
    """Real widgets mount asynchronously; ``wait_for`` is how you say so."""

    def test_without_waiting_an_async_widget_is_not_there_yet(self) -> None:
        evidence = UiProbe(
            _config(
                _widget_url(disclosure="yes", delay=_MOUNT_DELAY_MS),
                chat_selector="#chat-widget",
            )
        ).collect()

        text = evidence.turns[0].response.content
        assert "Widget wird geladen" in text
        assert "Sie chatten gerade mit einer KI" not in text

    def test_waiting_for_a_selector_catches_the_mounted_widget(self) -> None:
        evidence = UiProbe(
            _config(
                _widget_url(disclosure="yes", delay=_MOUNT_DELAY_MS),
                chat_selector="#chat-widget",
                wait_for="#banner",
            )
        ).collect()

        assert "Sie chatten gerade mit einer KI" in evidence.turns[0].response.content

    def test_waiting_a_fixed_number_of_milliseconds_also_works(self) -> None:
        evidence = UiProbe(
            _config(
                _widget_url(disclosure="yes", delay=300),
                chat_selector="#chat-widget",
                wait_for=2000,
            )
        ).collect()

        assert "Sie chatten gerade mit einer KI" in evidence.turns[0].response.content

    def test_a_selector_that_never_appears_is_reported_clearly(self) -> None:
        config = _config(
            _widget_url(disclosure="yes"), wait_for="#never-rendered", timeout_seconds=2
        )
        with pytest.raises(ProbeError, match="never became visible"):
            UiProbe(config).collect()


@needs_browser
@pytest.mark.ui
class TestFailureModes:
    """Playwright's exceptions never escape; every failure is a ProbeError."""

    def test_a_selector_matching_nothing_is_reported(self) -> None:
        config = _config(
            _widget_url(disclosure="yes"), chat_selector="#no-such-widget", timeout_seconds=5
        )
        with pytest.raises(ProbeError, match="matched no element"):
            UiProbe(config).collect()

    def test_an_unreachable_target_raises_probe_error(self) -> None:
        """Discard port 9: nothing listens there, by definition."""
        with pytest.raises(ProbeError) as excinfo:
            UiProbe(_config("http://127.0.0.1:9/widget.html", timeout_seconds=10)).collect()

        assert type(excinfo.value) is ProbeError
        assert "could not be loaded" in str(excinfo.value)

    def test_a_missing_file_is_reported(self) -> None:
        missing = (_WIDGET.parent / "does-not-exist.html").as_uri()
        with pytest.raises(ProbeError, match="could not be loaded"):
            UiProbe(_config(missing, timeout_seconds=10)).collect()

    def test_an_unusable_selector_is_reported(self) -> None:
        config = _config(_widget_url(disclosure="yes"), chat_selector="<<<not a selector")
        with pytest.raises(ProbeError):
            UiProbe(config).collect()


@needs_browser
@pytest.mark.ui
class TestHttpTarget:
    """The same widget over HTTP, where a status code exists to be recorded."""

    def test_the_http_status_is_recorded(self, widget_server: str) -> None:
        evidence = UiProbe(
            _config(f"{widget_server}/widget.html?disclosure=yes", chat_selector="#chat-widget")
        ).collect()

        assert evidence.turns[0].status_code == 200
        assert "Sie chatten gerade mit einer KI" in evidence.turns[0].response.content

    def test_an_error_page_is_not_the_interface_under_test(self, widget_server: str) -> None:
        with pytest.raises(ProbeError, match="HTTP 404"):
            UiProbe(_config(f"{widget_server}/nope.html")).collect()


@needs_browser
@pytest.mark.ui
@pytest.mark.determinism
class TestDeterminism:
    """What is reproducible here, and what is honestly not."""

    def test_the_extracted_text_is_stable_across_runs(self) -> None:
        """The text is the authoritative evidence, so it is the thing pinned."""
        config = _config(_widget_url(disclosure="yes"), chat_selector="#chat-widget")
        first = UiProbe(config).collect().turns[0]
        second = UiProbe(config).collect().turns[0]

        assert first.response.content == second.response.content
        assert first.response_sha256 == second.response_sha256

    def test_screenshots_share_dimensions_but_are_not_promised_byte_equal(self) -> None:
        """Font rasterisation varies by machine, OS and Chromium build.

        The geometry is pinned and asserted; the bytes are not, and the module
        docstring says so rather than letting a report imply a guarantee the
        renderer cannot give.
        """
        config = _config(_widget_url(disclosure="yes"))
        first = UiProbe(config).collect().turns[0].artifacts[0]
        second = UiProbe(config).collect().turns[0].artifacts[0]

        assert first.data is not None
        assert second.data is not None
        assert _png_dimensions(first.data) == _png_dimensions(second.data) == (1280, 800)
