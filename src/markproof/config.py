# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Pydantic model of the target config (``markproof.yaml``).

Mirrors ``examples/markproof.yaml``: a ``target`` with one or more probes
(``http-chat`` | ``ui`` | ``media``), a ``text_marking`` block (method,
watermark config path, detector), the selected ``rulepack``, and the ``report``
block (signing key source, output formats).

Secrets are never inlined: auth tokens and the SynthID watermark config are
referenced by environment variable or file path and resolved at run time.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ruamel.yaml import YAML

from markproof.rules.schema import ProbeKind

__all__ = [
    "AuthConfig",
    "ConfigError",
    "HttpChatProbeConfig",
    "MarkproofConfig",
    "MediaProbeConfig",
    "ProbeConfig",
    "ReportConfig",
    "TargetConfig",
    "TextMarkingConfig",
    "UiProbeConfig",
    "ViewportConfig",
    "load_config",
]

#: Languages with curated prompt sets and disclosure patterns in v0.1.
SUPPORTED_LANGS = ("de", "en")


class ConfigError(ValueError):
    """The config is unusable — malformed, or referencing something absent.

    Configuration problems are fatal on purpose. A tool that quietly skips a
    misconfigured probe reports a green run it never performed.
    """


class AuthConfig(BaseModel):
    """How to authenticate against the endpoint.

    The token itself never appears in the config file — only the name of the
    environment variable holding it. Keeps secrets out of git and out of the
    evidence bundle.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    header: str = Field(default="Authorization", min_length=1)
    env: str = Field(min_length=1)
    prefix: str = "Bearer "

    def resolve(self) -> tuple[str, str]:
        """Return the header name and value.

        Raises:
            ConfigError: if the environment variable is unset or empty.
        """
        token = os.environ.get(self.env, "")
        if not token:
            raise ConfigError(
                f"environment variable {self.env!r} is not set — "
                "it must hold the API token for this target"
            )
        return self.header, f"{self.prefix}{token}"


class HttpChatProbeConfig(BaseModel):
    """An OpenAI-compatible (or generic JSON) chat endpoint to probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    type: Literal["http-chat"]
    url: str = Field(min_length=1)
    dialect: Literal["openai-chat", "generic-json"] = "openai-chat"
    lang: str = "de"
    model: str = "gpt-4o-mini"
    auth: AuthConfig | None = None
    prompts_file: str | None = None
    response_path: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @property
    def probe_kind(self) -> ProbeKind:
        return ProbeKind.HTTP_CHAT

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("lang")
    @classmethod
    def _supported_lang(cls, v: str) -> str:
        if v not in SUPPORTED_LANGS:
            raise ValueError(f"lang {v!r} is not supported (have: {', '.join(SUPPORTED_LANGS)})")
        return v

    @model_validator(mode="after")
    def _generic_needs_path(self) -> HttpChatProbeConfig:
        if self.dialect == "generic-json" and not self.response_path:
            raise ValueError(
                "dialect 'generic-json' requires 'response_path' "
                "(dotted path to the assistant text, e.g. 'data.reply')"
            )
        return self


class ViewportConfig(BaseModel):
    """The rendering box the UI probe fixes before it looks at anything.

    A pinned size is what makes two runs comparable: responsive layouts move a
    disclosure banner in and out of the fold, and a probe that inherited the
    CI runner's window would report a different interface on every machine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=800, ge=240, le=2160)


class UiProbeConfig(BaseModel):
    """A rendered chat interface to observe.

    The one probe kind that can answer ``before_first_user_message``: an API
    endpoint never speaks unprompted, a widget does. See ``probes/ui.py``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    type: Literal["ui"]
    url: str = Field(min_length=1)
    lang: str = "de"

    chat_selector: str | None = None
    """CSS selector for the widget, or None to read the whole page.

    It defines what counts as *the interface* for the text check, so a notice
    rendered outside it is not observed. Point it at the container that holds
    any disclosure the operator relies on — or leave it unset and let the whole
    page be the evidence.
    """

    wait_for: str | int | None = None
    """A CSS selector to wait for, or a number of milliseconds to sit still.

    Real widgets mount asynchronously, so the load event is often too early. A
    selector is the better instrument — it waits for a fact rather than for a
    guess about how slow the runner is — and a millisecond value is the escape
    hatch for interfaces that expose nothing to wait on.
    """

    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    prompt_id: str = Field(default="ui-initial-view", min_length=1)
    """Names the observation in the report. Not a prompt: the probe asks
    nothing, which is precisely what makes the turn a first turn."""

    @property
    def probe_kind(self) -> ProbeKind:
        return ProbeKind.UI

    @field_validator("url")
    @classmethod
    def _renderable_url(cls, v: str) -> str:
        # file:// is allowed here and nowhere else: the thing under test is a
        # rendered document, and a build artefact on disk is a legitimate — and
        # network-free — target for it.
        if not v.startswith(("http://", "https://", "file://")):
            raise ValueError("url must start with http://, https:// or file://")
        return v

    @field_validator("lang")
    @classmethod
    def _supported_lang(cls, v: str) -> str:
        if v not in SUPPORTED_LANGS:
            raise ValueError(f"lang {v!r} is not supported (have: {', '.join(SUPPORTED_LANGS)})")
        return v

    @field_validator("wait_for", mode="before")
    @classmethod
    def _not_a_flag(cls, v: object) -> object:
        # Must run before coercion: bool is an int in Python and pydantic will
        # happily read `wait_for: true` as a 1 ms pause. That is a mistake worth
        # naming, not a value worth honouring.
        if isinstance(v, bool):
            raise ValueError(
                "wait_for must be a CSS selector or a number of milliseconds, not a boolean"
            )
        return v

    @field_validator("wait_for")
    @classmethod
    def _usable_wait(cls, v: str | int | None) -> str | int | None:
        if isinstance(v, int):
            if not 0 <= v <= 60_000:
                raise ValueError("wait_for in milliseconds must be between 0 and 60000")
        elif isinstance(v, str) and not v.strip():
            raise ValueError("wait_for must not be blank; omit the field instead")
        return v


class MediaProbeConfig(BaseModel):
    """An image/media generation endpoint to probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    type: Literal["media"]
    url: str = Field(min_length=1)
    lang: str = "de"
    model: str = "dall-e-3"
    prompt: str = "Ein einfaches Testbild."
    prompt_id: str = "media-generation"
    size: str | None = None
    response_format: Literal["url", "b64_json"] = "url"
    expect_media_type: str | None = None
    auth: AuthConfig | None = None
    timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    """Generation is slower than chat, so the default timeout is longer."""

    @property
    def probe_kind(self) -> ProbeKind:
        return ProbeKind.MEDIA

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("lang")
    @classmethod
    def _supported_lang(cls, v: str) -> str:
        if v not in SUPPORTED_LANGS:
            raise ValueError(f"lang {v!r} is not supported (have: {', '.join(SUPPORTED_LANGS)})")
        return v


#: A probe entry in the config. Discriminated on ``type`` so an unknown probe
#: kind is a loud config error rather than a silently ignored block.
ProbeConfig = Annotated[
    HttpChatProbeConfig | UiProbeConfig | MediaProbeConfig, Field(discriminator="type")
]


class TargetConfig(BaseModel):
    """The system under test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    probes: tuple[ProbeConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_probe_ids(self) -> TargetConfig:
        seen: set[str] = set()
        for probe in self.probes:
            if probe.id in seen:
                raise ValueError(f"duplicate probe id {probe.id!r}")
            seen.add(probe.id)
        return self


class ReportConfig(BaseModel):
    """Where the report goes and how it is signed (fully used from M4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sign_key: str | None = None
    formats: tuple[Literal["json", "summary"], ...] = ("json", "summary")
    output_dir: str = "markproof-report"


class TextMarkingConfig(BaseModel):
    """Where to find the operator's watermark configuration.

    Kept out of the rulepack on purpose: a rulepack is public and citable, while
    these keys are a production secret — whoever holds them can verify *and*
    forge the mark.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["synthid", "none-declared"] = "synthid"
    watermark_config: str | None = None
    """Path to the JSON config. Required for ``method: synthid``."""

    @model_validator(mode="after")
    def _synthid_needs_config(self) -> TextMarkingConfig:
        if self.method == "synthid" and not self.watermark_config:
            raise ValueError(
                "text_marking.method 'synthid' requires 'watermark_config' — "
                "without the generation-side parameters no verdict is possible"
            )
        return self


class MarkproofConfig(BaseModel):
    """A complete ``markproof.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    target: TargetConfig
    rulepack: str = Field(min_length=1)
    text_marking: TextMarkingConfig | None = None
    report: ReportConfig = Field(default_factory=ReportConfig)


def load_config(path: Path) -> MarkproofConfig:
    """Load and validate ``markproof.yaml``.

    Raises:
        ConfigError: if the file is missing, is not a mapping, or fails
            validation. The message names the offending field.
    """
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")

    yaml = YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.load(fh)
    except Exception as exc:  # ruamel raises a family of parse errors
        raise ConfigError(f"{path}: could not parse YAML — {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a YAML mapping at the top level")

    try:
        return MarkproofConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"{path}: {exc}") from exc
