# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Media probe against mocked endpoints.

Covers both retrieval paths and the failure modes that look like success from
the outside — chiefly an error page served with status 200, which is how a
broken CDN presents itself.
"""

from __future__ import annotations

import base64
import struct
import zlib

import httpx
import pytest
import respx

from markproof.config import MediaProbeConfig
from markproof.probes.base import ProbeError
from markproof.probes.media import MediaProbe

_GEN_URL = "https://api.example.invalid/v1/images/generations"
_ASSET_URL = "https://cdn.example.invalid/generated/0.png"


def tiny_png(colour: tuple[int, int, int] = (200, 80, 60)) -> bytes:
    """A valid 8x8 PNG, built without an image library."""
    width = height = 8
    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _config(**kwargs: object) -> MediaProbeConfig:
    base: dict[str, object] = {"id": "img", "type": "media", "url": _GEN_URL}
    base.update(kwargs)
    return MediaProbeConfig(**base)  # type: ignore[arg-type]


class TestRetrievalPaths:
    @respx.mock
    def test_follows_a_returned_url(self) -> None:
        png = tiny_png()
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(200, json={"created": 1, "data": [{"url": _ASSET_URL}]})
        )
        respx.get(_ASSET_URL).mock(
            return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
        )

        evidence = MediaProbe(_config()).collect()
        artifacts = evidence.turns[0].artifacts
        assert len(artifacts) == 1
        assert artifacts[0].data == png
        assert artifacts[0].media_type == "image/png"
        assert artifacts[0].source_url == _ASSET_URL

    @respx.mock
    def test_decodes_inline_base64(self) -> None:
        png = tiny_png()
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={"created": 1, "data": [{"b64_json": base64.b64encode(png).decode()}]},
            )
        )
        evidence = MediaProbe(_config(response_format="b64_json")).collect()
        assert evidence.turns[0].artifacts[0].data == png

    @respx.mock
    def test_digest_matches_the_payload(self) -> None:
        """The digest is what ties a finding to bytes, so it must be computed, not claimed."""
        import hashlib

        png = tiny_png()
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(
                200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]}
            )
        )
        artifact = MediaProbe(_config()).collect().turns[0].artifacts[0]
        assert artifact.sha256 == hashlib.sha256(png).hexdigest()
        assert artifact.size_bytes == len(png)

    @respx.mock
    def test_several_assets_are_all_collected(self) -> None:
        png = tiny_png()
        encoded = base64.b64encode(png).decode()
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(
                200, json={"data": [{"b64_json": encoded}, {"b64_json": encoded}]}
            )
        )
        assert len(MediaProbe(_config()).collect().turns[0].artifacts) == 2


class TestFailureModes:
    @respx.mock
    def test_error_page_with_status_200_is_rejected(self) -> None:
        """The failure that looks like success: HTML where an image should be."""
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"url": _ASSET_URL}]})
        )
        respx.get(_ASSET_URL).mock(
            return_value=httpx.Response(
                200, content=b"<html>rate limited</html>", headers={"content-type": "text/html"}
            )
        )
        with pytest.raises(ProbeError, match="not media"):
            MediaProbe(_config()).collect()

    @respx.mock
    def test_missing_content_type_falls_back_to_the_url_suffix(self) -> None:
        """Some object stores serve images as application/octet-stream."""
        png = tiny_png()
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"url": _ASSET_URL}]})
        )
        respx.get(_ASSET_URL).mock(
            return_value=httpx.Response(
                200, content=png, headers={"content-type": "application/octet-stream"}
            )
        )
        assert MediaProbe(_config()).collect().turns[0].artifacts[0].media_type == "image/png"

    @respx.mock
    def test_empty_data_array_is_an_error_not_a_pass(self) -> None:
        """No asset means nothing was checked — never report that as clean."""
        respx.post(_GEN_URL).mock(return_value=httpx.Response(200, json={"data": []}))
        with pytest.raises(ProbeError, match="no media"):
            MediaProbe(_config()).collect()

    @respx.mock
    def test_non_json_response_is_reported_clearly(self) -> None:
        respx.post(_GEN_URL).mock(return_value=httpx.Response(200, content=b"not json"))
        with pytest.raises(ProbeError, match="not JSON"):
            MediaProbe(_config()).collect()

    @respx.mock
    def test_http_error_from_the_generator_is_reported(self) -> None:
        respx.post(_GEN_URL).mock(return_value=httpx.Response(429, json={"error": "slow down"}))
        with pytest.raises(ProbeError, match="HTTP 429"):
            MediaProbe(_config()).collect()

    @respx.mock
    def test_unreachable_endpoint_raises_probe_error_not_a_transport_error(self) -> None:
        respx.post(_GEN_URL).mock(side_effect=httpx.ConnectError("no route"))
        with pytest.raises(ProbeError, match="unreachable"):
            MediaProbe(_config()).collect()

    @respx.mock
    def test_invalid_base64_is_reported(self) -> None:
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(200, json={"data": [{"b64_json": "!!!not base64!!!"}]})
        )
        with pytest.raises(ProbeError, match="not valid base64"):
            MediaProbe(_config()).collect()


class TestEvidenceShape:
    @respx.mock
    def test_artifact_bytes_are_excluded_from_serialisation(self) -> None:
        """Evidence stays diffable; the digest carries the link to the payload."""
        png = tiny_png()
        respx.post(_GEN_URL).mock(
            return_value=httpx.Response(
                200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]}
            )
        )
        evidence = MediaProbe(_config()).collect()
        dumped = evidence.model_dump_json()
        assert "sha256" in dumped
        assert base64.b64encode(png).decode() not in dumped
        assert '"data"' not in dumped
