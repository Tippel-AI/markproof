# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Factories for hand-built evidence — no network, no clock, no randomness."""

from __future__ import annotations

from markproof.probes.base import ContentScope, Evidence, Message, Role, Turn, sha256_hex
from markproof.rules.schema import ProbeKind

__all__ = ["make_evidence", "make_turn", "make_ui_evidence"]


def make_turn(
    prompt_id: str,
    response_text: str,
    *,
    with_user_message: bool = False,
) -> Turn:
    """A single exchange.

    ``with_user_message=False`` models an unprompted opening — the case the
    ``before_first_user_message`` position cares about.
    """
    request = [Message(role=Role.USER, content="Hallo")] if with_user_message else []
    return Turn(
        prompt_id=prompt_id,
        request=request,
        response=Message(role=Role.ASSISTANT, content=response_text),
        response_sha256=sha256_hex(response_text),
        status_code=200,
    )


def make_evidence(*turns: Turn, lang: str = "de", probe_id: str = "chat") -> Evidence:
    """Evidence wrapping the given turns."""
    return Evidence(
        probe_id=probe_id,
        probe_kind=ProbeKind.HTTP_CHAT,
        target_name="test-target",
        lang=lang,
        turns=turns,
    )


def make_ui_evidence(
    page_text: str,
    *,
    content: str | None = None,
    selector: str = "article .body",
    lang: str = "de",
    probe_id: str = "page",
) -> Evidence:
    """A rendered-page observation, optionally with a named generated region.

    ``content=None`` models a UI probe configured without ``content_selector``:
    the page was read, but nothing says which part of it the model wrote.
    """
    return Evidence(
        probe_id=probe_id,
        probe_kind=ProbeKind.UI,
        target_name="test-target",
        lang=lang,
        turns=(make_turn("ui-initial-view", page_text),),
        content_scope=(
            ContentScope.of(content, selector=selector) if content is not None else None
        ),
    )
