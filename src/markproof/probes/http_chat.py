# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""HTTP chat probe — talks to the endpoint the way a user's client would.

Two dialects in v0.1: ``openai-chat`` (POST /chat/completions with the usual
``choices[0].message.content`` shape) and ``generic-json`` (any JSON body, with
a dotted ``response_path`` pointing at the assistant text).

The probe sends each prompt from the configured prompt set as a fresh, single
turn conversation. That is deliberate: Article 50(1) is about what a user meets
at the start, and a fresh conversation is the only reproducible way to observe
it. Multi-turn behaviour is a later milestone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

from markproof.config import HttpChatProbeConfig
from markproof.probes.base import (
    Evidence,
    Message,
    ProbeError,
    Role,
    Turn,
    sha256_hex,
)
from markproof.rules.schema import ProbeKind

__all__ = ["HttpChatProbe", "Prompt", "PromptSet", "load_prompt_set"]

#: Where the packaged default prompt sets live.
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class Prompt(BaseModel):
    """One question to put to the endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    role: str = "user"
    text: str = Field(min_length=1)
    purpose: str | None = None
    guideline_ref: str | None = None


class PromptSet(BaseModel):
    """A language-specific set of probe prompts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    lang: str = Field(pattern=r"^[a-z]{2}$")
    prompts: tuple[Prompt, ...] = Field(min_length=1)


def load_prompt_set(lang: str, override: Path | None = None) -> PromptSet:
    """Load the prompt set for a language, or an explicit file.

    Raises:
        ProbeError: if the file is missing or malformed.
    """
    path = override if override is not None else _PROMPTS_DIR / f"{lang}.yaml"
    if not path.is_file():
        raise ProbeError(f"prompt set not found: {path}")

    yaml = YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.load(fh)
        return PromptSet.model_validate(raw)
    except Exception as exc:
        raise ProbeError(f"{path}: invalid prompt set — {exc}") from exc


def _dig(payload: Any, dotted: str) -> Any:
    """Follow a dotted path through nested dicts and lists.

    ``choices.0.message.content`` walks dicts by key and lists by index.
    """
    current = payload
    for part in dotted.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ProbeError(f"response path {dotted!r}: no element {part!r}") from exc
        elif isinstance(current, dict):
            if part not in current:
                raise ProbeError(f"response path {dotted!r}: no key {part!r}")
            current = current[part]
        else:
            raise ProbeError(
                f"response path {dotted!r}: cannot descend into {type(current).__name__}"
            )
    return current


class HttpChatProbe:
    """Collects evidence from a chat endpoint."""

    def __init__(self, config: HttpChatProbeConfig, *, client: httpx.Client | None = None) -> None:
        self.config = config
        self.probe_id = config.id
        self.probe_kind = ProbeKind.HTTP_CHAT
        self._client = client
        self._prompt_set = load_prompt_set(
            config.lang,
            Path(config.prompts_file) if config.prompts_file else None,
        )

    def collect(self) -> Evidence:
        """Send every prompt as a fresh conversation and record what came back.

        Raises:
            ProbeError: on transport failures, non-2xx status, or a response
                body that does not contain assistant text where the dialect
                says it should.
        """
        client = self._client or httpx.Client(timeout=self.config.timeout_seconds)
        owns_client = self._client is None
        turns: list[Turn] = []

        try:
            for prompt in self._prompt_set.prompts:
                turns.append(self._one_turn(client, prompt))
        finally:
            if owns_client:
                client.close()

        return Evidence(
            probe_id=self.probe_id,
            probe_kind=self.probe_kind,
            target_name=self.config.id,
            lang=self.config.lang,
            turns=tuple(turns),
        )

    def _one_turn(self, client: httpx.Client, prompt: Prompt) -> Turn:
        """Perform a single request/response exchange."""
        request_messages = [Message(role=Role.USER, content=prompt.text)]
        headers = {"Content-Type": "application/json"}
        if self.config.auth is not None:
            name, value = self.config.auth.resolve()
            headers[name] = value

        body = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt.text}],
        }

        try:
            response = client.post(self.config.url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProbeError(f"{self.config.url} unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise ProbeError(
                f"{self.config.url} returned HTTP {response.status_code} for prompt {prompt.id!r}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProbeError(f"{self.config.url}: response is not JSON") from exc

        content = self._extract(payload)
        return Turn(
            prompt_id=prompt.id,
            request=request_messages,
            response=Message(role=Role.ASSISTANT, content=content),
            response_sha256=sha256_hex(content),
            status_code=response.status_code,
        )

    def _extract(self, payload: Any) -> str:
        """Pull the assistant text out of a response body."""
        path = (
            self.config.response_path
            if self.config.dialect == "generic-json"
            else "choices.0.message.content"
        )
        # ``response_path`` is validated as present for generic-json in the config model.
        value = _dig(payload, path or "choices.0.message.content")
        if not isinstance(value, str):
            raise ProbeError(
                f"response path {path!r} yielded {type(value).__name__}, expected a string"
            )
        return value
