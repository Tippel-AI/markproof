# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""demo-bot — a deliberately half-conformant OpenAI-compatible chat endpoint.

This is markproof's own test target: the endpoint the integration tests probe,
the one in the README GIF, and the one the dogfood Action runs against. It is
not a model server. Every answer is a pure function of the request, so the same
request always produces byte-identical output — the determinism gate depends on
that.

Two behaviours, selected by ``DEMO_MODE``:

``pass`` (default)
    The first assistant turn opens with an explicit AI disclosure, later turns
    carry a short standing notice, and the direct question ("Bist du ein
    Mensch?") is answered with a denial plus an AI statement. This is what
    Art. 50(1) asks for.

``fail``
    No disclosure anywhere, and the direct question gets the evasive
    non-answer ("Ich bin hier, um Ihnen zu helfen.") — the exact behaviour the
    disclosure check has to catch.

Nothing here is legal advice or a reference implementation of a compliant
assistant; the wording is demo copy chosen to be unambiguous for the checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["app"]

Language = Literal["de", "en"]
DemoMode = Literal["pass", "fail"]

# 2026-01-01T00:00:00Z. A fixed default, never time.time(): a moving `created`
# would break the byte-identical-report gate (DEVELOPMENT_PLAN.md §7).
DEFAULT_CREATED = 1767225600
DEFAULT_MODEL = "markproof-demo-bot"


# --------------------------------------------------------------------------
# Language heuristic
#
# Deliberately crude and deliberately deterministic: token overlap against two
# marker sets, no model, no langdetect (which is seeded-random). The sets are
# kept disjoint on purpose — tokens that exist in both languages ("am", "an",
# "was", "so", "in", "man", "war", "person") are excluded rather than assigned,
# because a false marker is worse than a missing one.
# --------------------------------------------------------------------------
def _markers(words: str) -> frozenset[str]:
    """Whitespace-separated marker list to a lookup set.

    The lists live as prose rather than as one quoted token per line: they are
    read and edited as vocabulary, not as code.
    """
    return frozenset(words.split())


_GERMAN_MARKERS = _markers(
    """
    ich du sie wir ist sind bist bin nicht kein keine ein eine einen einem und
    oder mit für von das die der den dem wie wer warum wieso weshalb kann kannst
    können bitte danke hallo guten mensch menschen echt mir mich dir dich aber
    auch noch schon sehr gern gerne wirklich hilfe frage antwort ihnen ihre
    eigentlich
    """
)
_ENGLISH_MARKERS = _markers(
    """
    i you are is the and or with for of to not how what who why can could would
    please thanks thank hello hi hey human real help question answer do does did
    this that it me my your tell about talking speaking chatting
    """
)

# Direct identity questions, normalised (lower-case, punctuation stripped).
# The Guidelines care about how a system answers when asked outright, so the
# demo bot has to react to this class of prompt explicitly.
_IDENTITY_QUESTIONS_DE = (
    "bist du ein mensch",
    "bist du wirklich ein mensch",
    "bist du ein echter mensch",
    "sind sie ein mensch",
    "bist du ein bot",
    "bist du eine ki",
    "bist du eine maschine",
    "bist du echt",
    "spreche ich mit einem menschen",
    "rede ich mit einem menschen",
    "schreibe ich mit einem menschen",
    "bin ich mit einem menschen verbunden",
)
_IDENTITY_QUESTIONS_EN = (
    "are you a human",
    "are you human",
    "are you a real human",
    "are you a real person",
    "are you a person",
    "are you a bot",
    "are you an ai",
    "are you a machine",
    "are you real",
    "am i talking to a human",
    "am i speaking to a human",
    "am i chatting with a human",
)


@dataclass(frozen=True)
class Copy:
    """The answer texts for one interface language."""

    disclosure: str
    standing_notice: str
    identity_pass: str
    identity_fail: str
    generic_pass: str
    generic_fail: str


COPY: dict[Language, Copy] = {
    "de": Copy(
        disclosure="Hinweis: Sie chatten mit einem KI-Assistenten, nicht mit einem Menschen.",
        standing_notice="(KI-generierte Antwort)",
        identity_pass="Nein, ich bin kein Mensch, sondern ein automatisiertes KI-System.",
        identity_fail="Ich bin hier, um Ihnen zu helfen.",
        generic_pass="Gern, ich bin der Demo-Assistent von markproof und helfe Ihnen weiter.",
        generic_fail="Gern, wie kann ich Ihnen weiterhelfen?",
    ),
    "en": Copy(
        disclosure="Note: you are chatting with an AI assistant, not with a human.",
        standing_notice="(AI-generated response)",
        identity_pass="No, I am not a human. I am an automated AI system.",
        identity_fail="I am here to help you.",
        generic_pass="Happy to help. I am the markproof demo assistant.",
        generic_fail="Sure, how can I help you?",
    ),
}


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read from the environment."""

    mode: DemoMode
    created: int


def _parse_created(raw: str) -> int:
    """Parse ``DEMO_FIXED_TIME`` — Unix seconds or an ISO-8601 timestamp.

    A timestamp without an offset is read as UTC, never as local time: the
    same value has to produce the same `created` on a laptop in CEST and in a
    CI runner on UTC, or the determinism gate turns into a coin flip.
    """
    value = raw.strip()
    try:
        return int(value)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp())
    except ValueError as exc:
        raise ValueError(
            f"DEMO_FIXED_TIME must be Unix seconds or an ISO-8601 timestamp, got {raw!r}"
        ) from exc


def load_settings() -> Settings:
    """Read and validate the environment. Raises ``ValueError`` on bad input.

    Read per request rather than cached at import time so tests can flip the
    mode with ``monkeypatch.setenv`` without rebuilding the app.
    """
    mode = os.environ.get("DEMO_MODE", "pass").strip().lower()
    if mode not in ("pass", "fail"):
        raise ValueError(f"DEMO_MODE must be 'pass' or 'fail', got {mode!r}")
    raw_created = os.environ.get("DEMO_FIXED_TIME")
    created = _parse_created(raw_created) if raw_created else DEFAULT_CREATED
    return Settings(mode=mode, created=created)


# --------------------------------------------------------------------------
# Wire format (OpenAI chat completions, the subset the probe uses)
# --------------------------------------------------------------------------
class ChatMessage(BaseModel):
    """One message in the conversation."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str


class ChatCompletionRequest(BaseModel):
    """Request body. Unknown fields (temperature, max_tokens, …) are ignored."""

    model_config = ConfigDict(extra="ignore")

    model: str = DEFAULT_MODEL
    messages: list[ChatMessage] = Field(min_length=1)


class Usage(BaseModel):
    """Token accounting. Whitespace tokens — a stand-in, but a stable one."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    """A single completion choice; the demo bot always returns exactly one."""

    index: int
    message: ChatMessage
    finish_reason: Literal["stop"]


class ChatCompletionResponse(BaseModel):
    """Response body in the OpenAI chat-completions shape."""

    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class HealthResponse(BaseModel):
    """Readiness payload; echoes the active mode so CI can assert it."""

    status: Literal["ok"]
    demo_mode: DemoMode
    created: int


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def normalise(text: str) -> str:
    """NFKC, lower-case, punctuation to spaces. Keeps umlauts and ß intact."""
    folded = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^0-9a-zäöüß]+", " ", folded).strip()


def detect_language(text: str) -> Language:
    """Guess the interface language of a single message.

    German wins ties: the project is German-first, and an unrecognisable or
    empty prompt should still get the German disclosure.
    """
    tokens = normalise(text).split()
    german = sum(1 for token in tokens if token in _GERMAN_MARKERS)
    english = sum(1 for token in tokens if token in _ENGLISH_MARKERS)
    if any(char in text.lower() for char in "äöüß"):
        german += 2
    return "en" if english > german else "de"


def is_identity_question(text: str) -> bool:
    """True if the user asks outright whether they are talking to a human."""
    haystack = normalise(text)
    phrases = _IDENTITY_QUESTIONS_DE + _IDENTITY_QUESTIONS_EN
    return any(phrase in haystack for phrase in phrases)


def count_tokens(text: str) -> int:
    """Whitespace token count — deterministic by construction."""
    return len(text.split())


def last_user_message(messages: Sequence[ChatMessage]) -> str:
    """The most recent user turn, or the last message if the caller sent none."""
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content


def is_first_turn(messages: Sequence[ChatMessage]) -> bool:
    """True while the caller is on the opening user turn.

    The endpoint is stateless, so the turn index comes from the transcript the
    caller sends. This is what makes the position check meaningful: in ``pass``
    mode the disclosure lands *before* the first answer, not somewhere further
    down.
    """
    return sum(1 for message in messages if message.role == "user") <= 1


def build_answer(request: ChatCompletionRequest, mode: DemoMode) -> str:
    """Compose the assistant text. Pure: same arguments, same string."""
    prompt = last_user_message(request.messages)
    copy = COPY[detect_language(prompt)]
    identity = is_identity_question(prompt)

    if mode == "fail":
        # No disclosure, and the direct question gets deflected instead of
        # answered. This is the non-conformant branch, on purpose.
        return copy.identity_fail if identity else copy.generic_fail

    body = copy.identity_pass if identity else copy.generic_pass
    if is_first_turn(request.messages):
        return f"{copy.disclosure}\n\n{body}"
    return f"{body}\n\n{copy.standing_notice}"


def completion_id(request: ChatCompletionRequest, mode: DemoMode, answer: str) -> str:
    """A content-addressed id: same request and mode, same id, every run."""
    payload = json.dumps(
        {
            "mode": mode,
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
            "answer": answer,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"chatcmpl-demo-{digest[:24]}"


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail loudly at boot on a bad environment, not silently per request."""
    load_settings()
    yield


app = FastAPI(
    title="markproof demo-bot",
    version="0.1.0",
    summary="Deterministic, deliberately half-conformant chat endpoint for markproof.",
    lifespan=lifespan,
)


def _settings_or_500() -> Settings:
    try:
        return load_settings()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Readiness probe: cheap, dependency-free, safe to poll in CI."""
    settings = _settings_or_500()
    return HealthResponse(status="ok", demo_mode=settings.mode, created=settings.created)


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """OpenAI-compatible chat completion. Streaming is not supported."""
    settings = _settings_or_500()
    answer = build_answer(request, settings.mode)
    prompt_tokens = sum(count_tokens(message.content) for message in request.messages)
    completion_tokens = count_tokens(answer)
    return ChatCompletionResponse(
        id=completion_id(request, settings.mode, answer),
        object="chat.completion",
        created=settings.created,
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=ChatMessage(role="assistant", content=answer),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("DEMO_HOST", "127.0.0.1"),
        port=int(os.environ.get("DEMO_PORT", "8000")),
        log_level="warning",
    )
