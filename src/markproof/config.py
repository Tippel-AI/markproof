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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ruamel.yaml import YAML

from markproof.rules.schema import ProbeKind

__all__ = [
    "AuthConfig",
    "ConfigError",
    "HttpChatProbeConfig",
    "MarkproofConfig",
    "ReportConfig",
    "TargetConfig",
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


class TargetConfig(BaseModel):
    """The system under test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    probes: tuple[HttpChatProbeConfig, ...] = Field(min_length=1)

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


class MarkproofConfig(BaseModel):
    """A complete ``markproof.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    target: TargetConfig
    rulepack: str = Field(min_length=1)
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
