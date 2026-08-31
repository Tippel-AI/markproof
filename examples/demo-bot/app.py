# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""demo-bot — a deliberately half-conformant OpenAI-compatible endpoint.

This is markproof's own test target: the endpoint the integration tests probe,
the one in the README GIF, and the one the dogfood Action runs against. It is
not a model server. Every answer is a pure function of the request, so the same
request always produces byte-identical output — the determinism gate depends on
that.

Behaviour is selected by ``DEMO_MODE``:

``pass`` (default)
    The first assistant turn opens with an explicit AI disclosure, later turns
    carry a short standing notice, and the direct question ("Bist du ein
    Mensch?") is answered with a denial plus an AI statement. This is what
    Art. 50(1) asks for. Generated images carry a valid C2PA manifest whose
    action declares ``digitalSourceType = trainedAlgorithmicMedia``, which is
    what Art. 50(2) asks for. The answer text is additionally *watermarked*:
    its token sequence carries a SynthID-style mark under the config in
    ``watermark_config.demo.json``.

``fail``
    No disclosure anywhere, and the direct question gets the evasive
    non-answer ("Ich bin hier, um Ihnen zu helfen.") — the exact behaviour the
    disclosure check has to catch. Generated images carry no manifest at all:
    the common real failure, where a CDN or an image pipeline re-encoded the
    asset and dropped the C2PA chunk somewhere between the model and the user.

``wrongtype``
    A media-only variant. The chat side is identical to ``pass``; the image
    endpoint serves an asset whose manifest is present and cryptographically
    valid but whose action claims ``algorithmicMedia`` — algorithmically
    produced, but *not* by a trained model. It passes every "is this signed?"
    check and still misses the Art. 50(2) obligation, which is the case only
    an assertion-level check catches.

``nomark``
    A text-marking-only variant, and the control the M3 check is measured
    against. Chat answers disclose exactly as in ``pass`` and images are the
    same correctly signed asset, but the answer text carries **no watermark**.
    It exists so that a text-marking finding cannot be confused with a
    disclosure finding: ``pass`` and ``nomark`` differ in the token sequence
    and in nothing else — same anchors, same length, same register, same
    lattice of phrasings — so a detector that separates them is reading the
    marking rather than the wording.

Images are served from ``media/``, signed once offline by
``media/make_fixtures.py``. Signing per request would put a fresh ECDSA nonce
and a fresh signing time in every response, so the same request would never
return the same bytes twice.

Answer texts are served from ``text/``, marked once offline by
``text/make_texts.py``, for the same reason and one more: marking is a search
over wordings, and a bot that searched per request would make its own output
depend on the tokenizer and torch build installed that day.

Nothing here is legal advice or a reference implementation of a compliant
assistant; the wording is demo copy chosen to be unambiguous for the checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from base64 import b64encode
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["app"]

Language = Literal["de", "en"]
DemoMode = Literal["pass", "fail", "wrongtype", "nomark"]
DEMO_MODES: tuple[DemoMode, ...] = ("pass", "fail", "wrongtype", "nomark")

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
    """The answer texts for one interface language.

    Two groups with different jobs. ``identity_fail`` and ``generic_fail`` are
    served verbatim in ``fail`` mode. The other three are *anchors*: sentences
    that every conformant answer has to contain, whichever mode produced it.
    The long texts in ``text/`` embed them, and ``load_texts`` refuses to start
    the bot if one has gone missing — the disclosure rules read those sentences,
    so a regenerated text that dropped one would leave a bot that still answers
    and no longer discloses.
    """

    disclosure: str
    standing_notice: str
    identity_pass: str
    identity_fail: str
    generic_fail: str


COPY: dict[Language, Copy] = {
    "de": Copy(
        disclosure="Hinweis: Sie chatten mit einem KI-Assistenten, nicht mit einem Menschen.",
        standing_notice="(KI-generierte Antwort)",
        identity_pass="Nein, ich bin kein Mensch, sondern ein automatisiertes KI-System.",
        identity_fail="Ich bin hier, um Ihnen zu helfen.",
        generic_fail="Gern, wie kann ich Ihnen weiterhelfen?",
    ),
    "en": Copy(
        disclosure="Note: you are chatting with an AI assistant, not with a human.",
        standing_notice="(AI-generated response)",
        identity_pass="No, I am not a human. I am an automated AI system.",
        identity_fail="I am here to help you.",
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
    public_base_url: str | None


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


def _parse_base_url(raw: str) -> str:
    """Parse ``DEMO_PUBLIC_BASE_URL`` — the origin image URLs are built on."""
    value = raw.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"DEMO_PUBLIC_BASE_URL must be an http(s) URL, got {raw!r}")
    return value


def load_settings() -> Settings:
    """Read and validate the environment. Raises ``ValueError`` on bad input.

    Read per request rather than cached at import time so tests can flip the
    mode with ``monkeypatch.setenv`` without rebuilding the app.
    """
    mode = os.environ.get("DEMO_MODE", "pass").strip().lower()
    if mode not in DEMO_MODES:
        allowed = ", ".join(repr(name) for name in DEMO_MODES)
        raise ValueError(f"DEMO_MODE must be one of {allowed}, got {mode!r}")
    raw_created = os.environ.get("DEMO_FIXED_TIME")
    created = _parse_created(raw_created) if raw_created else DEFAULT_CREATED
    raw_base_url = os.environ.get("DEMO_PUBLIC_BASE_URL")
    base_url = _parse_base_url(raw_base_url) if raw_base_url else None
    return Settings(mode=mode, created=created, public_base_url=base_url)


# --------------------------------------------------------------------------
# Media fixtures
#
# The image endpoint hands out files that were signed once, offline, by
# media/make_fixtures.py — see that script for how they are built and why
# every pixel in them is our own production. Signing at request time would
# mean a fresh ECDSA nonce and a fresh signing time per response: the same
# request would never return the same bytes twice, and the determinism gate
# would be measuring the random number generator instead of the endpoint.
# --------------------------------------------------------------------------
MEDIA_DIR = Path(__file__).resolve().parent / "media"
IMAGE_MEDIA_TYPE = "image/png"

#: The fixtures are pre-rendered at this size; a `size` in the request cannot
#: change it, because changing it would mean re-rendering and re-signing.
IMAGE_SIZE = "512x512"

#: Which asset a mode hands out. All three stay reachable by name under
#: /media — the mode decides what the *generation* endpoint points at, not
#: what the download endpoint will serve.
#:
#: ``nomark`` serves the correctly signed image on purpose. Its defect is in
#: the text, and a mode that also broke the media would stop isolating it —
#: the same reasoning that keeps ``wrongtype``'s chat side conformant.
MEDIA_BY_MODE: dict[DemoMode, str] = {
    "pass": "demo-signed.png",
    "fail": "demo-unsigned.png",
    "wrongtype": "demo-wrongtype.png",
    "nomark": "demo-signed.png",
}


@cache
def load_media() -> dict[str, bytes]:
    """Read the fixtures once, on first use. Cached: the bytes never change.

    A missing file raises rather than 404s at request time — a demo bot
    without its assets is not a usable target, and ``lifespan`` calls this so
    the complaint lands at startup next to the other environment checks.
    """
    assets: dict[str, bytes] = {}
    for name in MEDIA_BY_MODE.values():
        path = MEDIA_DIR / name
        if not path.is_file():
            raise ValueError(
                f"missing media fixture {path} — regenerate the assets with "
                f"`python {MEDIA_DIR.name}/make_fixtures.py`"
            )
        assets[name] = path.read_bytes()
    return assets


# --------------------------------------------------------------------------
# Answer texts
#
# The chat endpoint hands out texts that were composed once, offline, by
# text/make_texts.py — see that script for how the marking is built and why
# every phrase in them is our own production. Marking at request time would
# mean running a search over wordings inside the request path, so the same
# request would return the same bytes only for as long as the tokenizer and
# the torch build stayed put.
#
# Four variants per language, because the answer depends on two things the
# endpoint can read off a stateless request: whether the user asked outright
# what they are talking to, and whether this is the opening turn.
# --------------------------------------------------------------------------
TEXT_DIR = Path(__file__).resolve().parent / "text"

#: Which rendering a mode serves. ``fail`` is absent: it answers from ``COPY``
#: with the short, undisclosed lines, and giving it a long text would confuse
#: the disclosure fixture with the marking one.
TEXT_VARIANT_BY_MODE: dict[DemoMode, str] = {
    "pass": "marked",
    "wrongtype": "marked",
    "nomark": "plain",
}

#: Spelled out again here rather than imported from ``text/lattice.py``: that
#: module is a development tool and pulls in transformers, while this app runs
#: on the three pinned packages in requirements.txt. The two lists have to
#: agree, and the startup check below is what enforces it — a variant this app
#: expects and the generator did not write stops the bot at boot.
KINDS = ("generic", "identity")
TURNS = ("first", "later")


def required_anchors(language: Language, kind: str, turn: str) -> tuple[str, ...]:
    """The sentences this variant must contain, whichever mode rendered it.

    On the opening turn the disclosure has to be present, because that is the
    turn the position rule reads. On a later turn the standing notice carries
    the disclosure instead. An identity question additionally has to be
    answered with the denial, which is the situation the Guidelines call out
    explicitly.
    """
    copy = COPY[language]
    anchors = [copy.disclosure] if turn == "first" else [copy.standing_notice]
    if kind == "identity":
        anchors.append(copy.identity_pass)
    return tuple(anchors)


@cache
def load_texts() -> dict[str, str]:
    """Read the answer texts once, on first use. Cached: they never change.

    Keyed ``<variant>/<lang>-<kind>-<turn>``. A missing file or a missing
    anchor raises rather than 404s at request time — ``lifespan`` calls this,
    so the complaint lands at startup next to the other environment checks.
    """
    texts: dict[str, str] = {}
    for variant in sorted(set(TEXT_VARIANT_BY_MODE.values())):
        for language in ("de", "en"):
            for kind in KINDS:
                for turn in TURNS:
                    name = f"{language}-{kind}-{turn}"
                    path = TEXT_DIR / variant / f"{name}.txt"
                    if not path.is_file():
                        raise ValueError(
                            f"missing answer text {path} — regenerate the texts with "
                            f"`python {TEXT_DIR.name}/make_texts.py`"
                        )
                    text = path.read_text(encoding="utf-8").strip()
                    for anchor in required_anchors(language, kind, turn):
                        if anchor not in text:
                            raise ValueError(
                                f"answer text {path} no longer contains the required "
                                f"sentence {anchor!r} — a bot that cannot disclose is "
                                f"not a conformant demo target"
                            )
                    texts[f"{variant}/{name}"] = text
    return texts


# --------------------------------------------------------------------------
# Wire format (OpenAI chat completions and images, the subset the probes use)
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


class ImageGenerationRequest(BaseModel):
    """Request body for the images endpoint, in the OpenAI images shape."""

    model_config = ConfigDict(extra="ignore")

    model: str = DEFAULT_MODEL
    prompt: str = Field(min_length=1)
    n: int = Field(default=1, ge=1, le=10)
    #: Accepted and ignored. The one asset per mode is pre-rendered at
    #: ``IMAGE_SIZE``; honouring another size would mean rendering and signing
    #: per request, which is exactly what determinism rules out here.
    size: str = IMAGE_SIZE
    #: Both delivery paths exist because markproof has to handle both: an
    #: asset behind a URL and one inlined in the JSON body.
    response_format: Literal["url", "b64_json"] = "url"


class ImageDatum(BaseModel):
    """One generated image: a URL or the bytes inline, never both."""

    url: str | None = None
    b64_json: str | None = None


class ImageGenerationResponse(BaseModel):
    """Response body in the OpenAI images shape."""

    created: int
    data: list[ImageDatum]


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


def answer_variant(request: ChatCompletionRequest) -> tuple[Language, str, str]:
    """Which stored text answers this request: language, kind and turn."""
    prompt = last_user_message(request.messages)
    kind = "identity" if is_identity_question(prompt) else "generic"
    turn = "first" if is_first_turn(request.messages) else "later"
    return detect_language(prompt), kind, turn


def build_answer(request: ChatCompletionRequest, mode: DemoMode) -> str:
    """Compose the assistant text. Pure: same arguments, same string."""
    if mode == "fail":
        # No disclosure, and the direct question gets deflected instead of
        # answered. This is the non-conformant branch, on purpose. It stays
        # short: the long texts exist to give a *text-marking* check something
        # to measure, and this mode is the disclosure fixture.
        prompt = last_user_message(request.messages)
        copy = COPY[detect_language(prompt)]
        return copy.identity_fail if is_identity_question(prompt) else copy.generic_fail

    # ``wrongtype`` lands here with ``pass``: its defect is in the manifest of
    # the image it serves, and a mode that broke the chat too would stop
    # isolating that defect. ``nomark`` differs from both only in which
    # rendering of the same lattice it serves.
    language, kind, turn = answer_variant(request)
    return load_texts()[f"{TEXT_VARIANT_BY_MODE[mode]}/{language}-{kind}-{turn}"]


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
    load_media()
    load_texts()
    yield


app = FastAPI(
    title="markproof demo-bot",
    version="0.1.0",
    summary="Deterministic, deliberately half-conformant chat and image endpoint for markproof.",
    lifespan=lifespan,
)


def _settings_or_500() -> Settings:
    try:
        return load_settings()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _media_or_500() -> dict[str, bytes]:
    try:
        return load_media()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _answer_or_500(request: ChatCompletionRequest, mode: DemoMode) -> str:
    try:
        return build_answer(request, mode)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def media_url(http_request: Request, settings: Settings, name: str) -> str:
    """Absolute URL of a stored asset.

    Built from the origin the caller reached us on, which is what a probe
    behind a port mapping needs. ``DEMO_PUBLIC_BASE_URL`` pins it instead when
    the address the outside world uses is not the bound one — a container, a
    tunnel, a reverse proxy — or when a test wants a response that does not
    move with the Host header.
    """
    if settings.public_base_url:
        return f"{settings.public_base_url}/media/{name}"
    return str(http_request.url_for("get_media", name=name))


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Readiness probe: cheap, dependency-free, safe to poll in CI."""
    settings = _settings_or_500()
    return HealthResponse(status="ok", demo_mode=settings.mode, created=settings.created)


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """OpenAI-compatible chat completion. Streaming is not supported."""
    settings = _settings_or_500()
    answer = _answer_or_500(request, settings.mode)
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


@app.post(
    "/v1/images/generations",
    response_model=ImageGenerationResponse,
    response_model_exclude_none=True,
)
def image_generations(
    request: ImageGenerationRequest, http_request: Request
) -> ImageGenerationResponse:
    """OpenAI-compatible image generation, served from the stored fixtures.

    The prompt is read and discarded: there is no model here, and the whole
    point of the endpoint is that the mode — not the prompt — decides what
    provenance the returned asset carries.
    """
    settings = _settings_or_500()
    assets = _media_or_500()
    name = MEDIA_BY_MODE[settings.mode]

    if request.response_format == "b64_json":
        datum = ImageDatum(b64_json=b64encode(assets[name]).decode("ascii"))
    else:
        datum = ImageDatum(url=media_url(http_request, settings, name))

    # One asset per mode, so `n` repeats it rather than varying it. A demo
    # that returned n different images would have to generate them.
    return ImageGenerationResponse(created=settings.created, data=[datum] * request.n)


@app.get(
    "/media/{name}",
    response_class=Response,
    responses={200: {"content": {IMAGE_MEDIA_TYPE: {}}, "description": "The stored asset."}},
)
def get_media(name: str) -> Response:
    """Serve one stored asset, byte for byte.

    The name is looked up in a dictionary of assets read at startup, never
    joined onto a filesystem path, so no request can walk out of ``media/``.
    Bytes go out untouched: re-encoding an image would break the C2PA hash
    bindings and turn a valid manifest into a tampering finding.

    All assets are reachable here regardless of mode. Only the generation
    endpoint above switches with ``DEMO_MODE``.
    """
    data = _media_or_500().get(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"no such media asset: {name!r}")
    return Response(content=data, media_type=IMAGE_MEDIA_TYPE)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("DEMO_HOST", "127.0.0.1"),
        port=int(os.environ.get("DEMO_PORT", "8000")),
        log_level="warning",
    )
