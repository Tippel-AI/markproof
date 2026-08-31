# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Media probe — fetches what an image endpoint actually delivers.

Asks the endpoint to generate media, then retrieves the bytes the way a user's
client would: following the returned URL, or decoding the inline base64. Both
paths matter, because the manifest usually survives one and not the other — a
URL is served through a CDN that may re-encode, while base64 comes straight from
the generator.

The probe stores bytes and digests. Whether a manifest is present, valid, and
marked as AI-generated is decided in ``checks/c2pa_verify.py``.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx

from markproof.config import MediaProbeConfig
from markproof.probes.base import (
    Artifact,
    Evidence,
    Message,
    ProbeError,
    Role,
    Turn,
    sha256_hex,
)
from markproof.rules.schema import ProbeKind

__all__ = ["MediaProbe"]

#: Content types the probe accepts as media. Anything else is reported rather
#: than guessed at — an HTML error page with status 200 is a common failure.
_MEDIA_PREFIXES = ("image/", "video/", "audio/")

#: Fallback when a server sends media without a usable Content-Type.
_EXTENSION_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".wav": "audio/wav",
}


class MediaProbe:
    """Collects generated media from an endpoint."""

    def __init__(self, config: MediaProbeConfig, *, client: httpx.Client | None = None) -> None:
        self.config = config
        self.probe_id = config.id
        self.probe_kind = ProbeKind.MEDIA
        self._client = client

    def collect(self) -> Evidence:
        """Generate media and retrieve every returned asset.

        Raises:
            ProbeError: if the endpoint is unreachable, answers with a non-2xx
                status, returns something other than JSON, or returns no asset
                at all.
        """
        client = self._client or httpx.Client(
            timeout=self.config.timeout_seconds, follow_redirects=True
        )
        owns_client = self._client is None
        try:
            turn = self._generate(client)
        finally:
            if owns_client:
                client.close()

        return Evidence(
            probe_id=self.probe_id,
            probe_kind=self.probe_kind,
            target_name=self.config.id,
            lang=self.config.lang,
            turns=(turn,),
        )

    def _generate(self, client: httpx.Client) -> Turn:
        """Ask for media and collect the assets that come back."""
        headers = {"Content-Type": "application/json"}
        if self.config.auth is not None:
            name, value = self.config.auth.resolve()
            headers[name] = value

        body: dict[str, Any] = {
            "model": self.config.model,
            "prompt": self.config.prompt,
            "n": 1,
            "response_format": self.config.response_format,
        }
        if self.config.size:
            body["size"] = self.config.size

        try:
            response = client.post(self.config.url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProbeError(f"{self.config.url} unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise ProbeError(f"{self.config.url} returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProbeError(f"{self.config.url}: response is not JSON") from exc

        artifacts = self._artifacts_from(payload, client)
        if not artifacts:
            raise ProbeError(
                f"{self.config.url}: response contained no media "
                "(expected data[].url or data[].b64_json)"
            )

        summary = f"{len(artifacts)} asset(s): " + ", ".join(a.id for a in artifacts)
        return Turn(
            prompt_id=self.config.prompt_id,
            request=[Message(role=Role.USER, content=self.config.prompt)],
            response=Message(role=Role.ASSISTANT, content=summary),
            response_sha256=sha256_hex(summary),
            status_code=response.status_code,
            artifacts=artifacts,
        )

    def _artifacts_from(self, payload: Any, client: httpx.Client) -> tuple[Artifact, ...]:
        """Turn an images-API response into artefacts, fetching URLs as needed."""
        if not isinstance(payload, dict):
            raise ProbeError("expected a JSON object at the top level of the response")

        entries = payload.get("data")
        if not isinstance(entries, list):
            raise ProbeError("response has no 'data' array")

        artifacts: list[Artifact] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if isinstance(entry.get("b64_json"), str):
                artifacts.append(self._from_base64(entry["b64_json"], index))
            elif isinstance(entry.get("url"), str):
                artifacts.append(self._from_url(entry["url"], index, client))
        return tuple(artifacts)

    def _from_base64(self, encoded: str, index: int) -> Artifact:
        """Decode an inline asset."""
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProbeError(f"data[{index}].b64_json is not valid base64: {exc}") from exc
        return Artifact.of(
            data,
            artifact_id=f"{self.probe_id}-{index}",
            media_type=self.config.expect_media_type or "image/png",
        )

    def _from_url(self, url: str, index: int, client: httpx.Client) -> Artifact:
        """Fetch an asset the way a browser would."""
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise ProbeError(f"could not fetch asset {url}: {exc}") from exc

        if response.status_code >= 400:
            raise ProbeError(f"asset {url} returned HTTP {response.status_code}")

        media_type = response.headers.get("content-type", "").split(";")[0].strip()
        if not media_type.startswith(_MEDIA_PREFIXES):
            guessed = self._guess_type(url)
            if guessed is None:
                raise ProbeError(
                    f"asset {url} has content type {media_type!r}, which is not media — "
                    "an error page served with status 200 looks like this"
                )
            media_type = guessed

        return Artifact.of(
            response.content,
            artifact_id=f"{self.probe_id}-{index}",
            media_type=media_type,
            source_url=url,
        )

    @staticmethod
    def _guess_type(url: str) -> str | None:
        """Infer a media type from the URL suffix, or give up."""
        lowered = url.lower().split("?")[0]
        for suffix, media_type in _EXTENSION_TYPES.items():
            if lowered.endswith(suffix):
                return media_type
        return None
