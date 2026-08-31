# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""UI probe (optional extra ``[ui]``) — Playwright against a rendered interface.

Why this probe exists
---------------------
``MPF-D-002`` asks whether the disclosure is there *before* the user has typed
anything. No HTTP endpoint can answer that: an API is spoken to first, always,
so every turn a chat probe records already has a user message in front of it and
``position: before_first_user_message`` has nothing to inspect. A rendered
interface does greet on its own. This probe loads the page, reads what a person
would read at that moment, and files it as a turn with an **empty request list**
— which is what makes ``Turn.is_first`` true and the rule decidable at last.

Visibility, not the DOM
-----------------------
The recorded text is ``innerText`` of the widget (or of ``body`` when no
selector is configured), never ``innerHTML``. A notice inside a ``display:none``
element is in the document and in no rendering of it; calling that a disclosure
would let a broken deploy — or a deliberate one — pass. Where a ``chat_selector``
is configured the probe additionally asserts the element is actually visible,
and reports a hidden widget as a probe failure rather than as an empty page.

What is deterministic here, and what is not
-------------------------------------------
The probe pins everything it can: a fixed viewport, ``device_scale_factor: 1``,
a fixed locale and the UTC timezone, ``prefers-reduced-motion: reduce``, a
stylesheet that collapses every animation and transition to zero duration, and
Chromium flags that fix the colour profile and font hinting.

That makes the *extracted text* reproducible, and the extracted text is the
authoritative evidence: it is what the disclosure check matches, and what the
finding's digest covers. The screenshot is not byte-reproducible and this module
will not pretend otherwise — font rasterisation differs between machines, OS
versions and Chromium builds, so two honest runs can produce two PNGs with
different digests. The image is the human-readable annex: the thing an auditor
looks at to see whether a notice was there and how prominent it was. Reading it
as a checksum would be a mistake.

Disabling animations settles the page at the end state of every transition. That
errs in the operator's favour — a banner that would have faded in over two
seconds counts as present — which is the right direction for a tool that must
not manufacture failures. A disclosure that arrives only after the user acts is
a different case, and one this probe still reports as absent, because it is.

Optional by design: the extra pulls a browser at run time, so the default path
must never need it. Missing, it fails loudly with both install commands.
"""

from __future__ import annotations

import importlib
from typing import Any

from markproof.config import UiProbeConfig
from markproof.probes.base import (
    Artifact,
    ContentScope,
    Evidence,
    Message,
    ProbeError,
    Role,
    Turn,
    sha256_hex,
)
from markproof.rules.schema import ProbeKind

__all__ = ["UiProbe"]

#: Both halves of the install, because the second one catches people out: the
#: pip package ships a driver, not a browser, and the binaries are a separate
#: several-hundred-megabyte download.
_INSTALL_HINT = (
    "install the optional extra and the browser binaries:\n"
    "    pip install 'markproof[ui]'\n"
    "    playwright install chromium\n"
    "The browsers are NOT part of the pip package — the second command "
    "downloads them into the Playwright cache (half a gigabyte or so, "
    "depending on platform)."
)

#: Chromium flags that remove avoidable rendering variance. They narrow the gap
#: between two machines; they do not close it (see the module docstring).
_CHROMIUM_ARGS = (
    "--force-color-profile=srgb",
    "--font-render-hinting=none",
    "--disable-lcd-text",
    "--hide-scrollbars",
)

#: Belt to the ``reduced_motion`` braces: a page is free to ignore the media
#: query, and this stylesheet is not.
_FREEZE_CSS = """
*, *::before, *::after {
  animation-delay: 0s !important;
  animation-duration: 0s !important;
  animation-iteration-count: 1 !important;
  transition-delay: 0s !important;
  transition-duration: 0s !important;
  scroll-behavior: auto !important;
  caret-color: transparent !important;
}
"""

#: A locale has to be picked, and picking it from the probe language keeps the
#: choice visible in the config instead of inheriting the runner's environment.
_LOCALES = {"de": "de-DE", "en": "en-US"}

#: Recorded when the navigation carried no HTTP status at all — a ``file://``
#: document. Writing 200 there would be inventing a header nobody sent.
_NO_HTTP_STATUS = 0


def _load_playwright() -> Any:
    """Import ``playwright.sync_api``, or explain how to get it.

    Imported by name rather than with a static ``import``: Playwright is an
    optional dependency, so a static import would make the type checker demand
    it in every environment, including the ones that deliberately do without.

    Raises:
        ProbeError: if the extra is not installed.
    """
    try:
        return importlib.import_module("playwright.sync_api")
    except ImportError as exc:
        raise ProbeError(
            f"the UI probe needs Playwright, which is not installed — {_INSTALL_HINT}"
        ) from exc


class UiProbe:
    """Observes what a rendered interface shows before anyone types."""

    def __init__(self, config: UiProbeConfig) -> None:
        self.config = config
        self.probe_id = config.id
        self.probe_kind = ProbeKind.UI

    def collect(self) -> Evidence:
        """Render the page and record its opening state.

        Returns:
            Evidence holding exactly one turn: an unprompted response with an
            empty request list, the visible text as its content, and a PNG
            screenshot attached as an artefact. When ``content_selector`` names
            a generated region, its text is recorded alongside as a
            ``content_scope`` — the same observation, read more narrowly.

        Raises:
            ProbeError: for every failure — a missing extra, a browser that will
                not start, an unreachable or non-2xx page, a selector that
                matches nothing or matches something invisible. Playwright's own
                exceptions never escape this method: a browser that died is an
                operational finding, not a traceback in someone's CI log.
        """
        api = _load_playwright()

        try:
            with api.sync_playwright() as playwright:
                browser = self._launch(playwright)
                try:
                    turn, content_scope = self._observe(browser)
                finally:
                    browser.close()
        except ProbeError:
            raise
        except Exception as exc:
            # Playwright raises its own error hierarchy plus whatever the driver
            # transport produces. Catching broadly is the point: the contract of
            # a probe is that it either returns evidence or raises ProbeError.
            raise ProbeError(f"{self.config.url}: UI probe failed — {exc}") from exc

        return Evidence(
            probe_id=self.probe_id,
            probe_kind=self.probe_kind,
            target_name=self.config.id,
            lang=self.config.lang,
            turns=(turn,),
            content_scope=content_scope,
        )

    def _launch(self, playwright: Any) -> Any:
        """Start headless Chromium, or say plainly that it is not there."""
        try:
            return playwright.chromium.launch(headless=True, args=list(_CHROMIUM_ARGS))
        except Exception as exc:
            raise ProbeError(f"Chromium could not be started — {_INSTALL_HINT}\n({exc})") from exc

    def _observe(self, browser: Any) -> tuple[Turn, ContentScope | None]:
        """Load the page, freeze it, and record text plus screenshot."""
        timeout_ms = self.config.timeout_seconds * 1000
        context = browser.new_context(
            viewport={"width": self.config.viewport.width, "height": self.config.viewport.height},
            device_scale_factor=1,
            locale=_LOCALES.get(self.config.lang, "en-US"),
            timezone_id="UTC",
            reduced_motion="reduce",
            color_scheme="light",
        )
        context.set_default_timeout(timeout_ms)

        try:
            page = context.new_page()
            status = self._navigate(page)
            page.add_style_tag(content=_FREEZE_CSS)
            self._wait(page, timeout_ms)

            text = self._visible_text(page)
            content = self._content_text(page)
            screenshot = page.screenshot(
                type="png", animations="disabled", caret="hide", scale="css"
            )
        finally:
            context.close()

        artifact = Artifact.of(
            screenshot,
            artifact_id=f"{self.probe_id}-initial-view",
            media_type="image/png",
            source_url=self.config.url,
        )

        selector = self.config.content_selector
        scope = ContentScope.of(content, selector=selector) if selector is not None else None

        turn = Turn(
            prompt_id=self.config.prompt_id,
            # The empty list is the whole point of this probe: nothing was said
            # to the interface, so whatever it showed, it showed unprompted.
            request=[],
            response=Message(role=Role.ASSISTANT, content=text),
            response_sha256=sha256_hex(text),
            status_code=status,
            artifacts=(artifact,),
        )
        return turn, scope

    def _navigate(self, page: Any) -> int:
        """Go to the target and report the HTTP status it answered with."""
        try:
            response = page.goto(self.config.url, wait_until="load")
        except Exception as exc:
            raise ProbeError(f"{self.config.url} could not be loaded: {exc}") from exc

        if response is None:
            # Some navigations produce no response object at all (same-document
            # ones, and schemes the browser answers internally). Recording 0
            # says "no status was reported" instead of inventing a 200.
            return _NO_HTTP_STATUS

        status = int(response.status)
        if status >= 400:
            raise ProbeError(
                f"{self.config.url} returned HTTP {status} — "
                "an error page is not the interface under test"
            )
        return status

    def _wait(self, page: Any, timeout_ms: float) -> None:
        """Honour ``wait_for``: a selector to appear, or a fixed pause."""
        wait_for = self.config.wait_for
        if wait_for is None:
            return

        if isinstance(wait_for, int):
            page.wait_for_timeout(wait_for)
            return

        try:
            page.wait_for_selector(wait_for, state="visible", timeout=timeout_ms)
        except Exception as exc:
            raise ProbeError(
                f"{self.config.url}: wait_for selector {wait_for!r} never became visible "
                f"within {self.config.timeout_seconds}s — the interface did not finish "
                f"mounting, or the selector is wrong ({exc})"
            ) from exc

    def _visible_text(self, page: Any) -> str:
        """The text a person would read, scoped to the configured widget.

        ``inner_text`` is deliberate. It is the rendered text: it skips
        ``display: none`` subtrees, skips ``<template>`` content, and returns
        what the layout actually produced. ``inner_html`` would return the
        document's claims instead of its output.
        """
        selector = self.config.chat_selector
        if selector is None:
            return str(page.locator("body").inner_text()).strip()
        return self._text_of(page, selector, field="chat_selector")

    def _content_text(self, page: Any) -> str:
        """The generated region's text, or the empty string if none is configured.

        Scoped separately from the widget text on purpose — see
        ``UiProbeConfig.content_selector`` for why one selector cannot serve
        both the disclosure search and the watermark score.
        """
        selector = self.config.content_selector
        if selector is None:
            return ""
        return self._text_of(page, selector, field="content_selector")

    def _text_of(self, page: Any, selector: str, *, field: str) -> str:
        """Rendered text of the first element matching ``selector``.

        A selector that matches nothing, or matches something invisible, ends
        the probe. It is tempting to shrug and carry on with less evidence, but
        a stale selector after a frontend refactor is exactly the regression
        this tool is for, and a run that quietly checked an empty string would
        report it as compliance.
        """
        locator = page.locator(selector)
        try:
            count = int(locator.count())
        except Exception as exc:
            raise ProbeError(f"{field} {selector!r} is not a usable selector: {exc}") from exc

        if count == 0:
            raise ProbeError(
                f"{self.config.url}: {field} {selector!r} matched no element — "
                "the element did not render, or the selector is stale. Use 'wait_for' if "
                "the interface mounts asynchronously."
            )

        first = locator.first
        if not first.is_visible():
            raise ProbeError(
                f"{self.config.url}: {field} {selector!r} matched an element that is "
                "not visible — nothing a user can read is inside it. If the widget opens "
                "from a launcher, point it at the container that is rendered on load, or "
                "capture the whole page by leaving it unset."
            )

        # ``.first`` and nothing else: several matches mean the selector is
        # ambiguous, and quietly concatenating them would invent a page that
        # never existed. The first match in document order is the one a reader
        # meets first.
        return str(first.inner_text()).strip()
