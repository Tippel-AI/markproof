# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The endpoint under test must not decide where the operator's key goes.

Every probe attaches an operator-supplied auth header, and the clients used to
follow redirects unconditionally. httpx strips exactly one header on a cross-host
redirect — ``Authorization`` — while ``AuthConfig.header`` is configurable and the
two most common real alternatives are not it: Azure OpenAI uses ``api-key``, Azure
Functions ``x-functions-key``.

So answering a probe with ``302 Location: https://attacker.example/`` sent the
operator's production credential there. For a tool whose whole premise is "point
this at your live system with your real token", that is worse than any marking
failure it was built to catch: those cost compliance, this costs a key.

These tests are the audit's reproduction, kept.
"""

from __future__ import annotations

import contextlib

import httpx
import pytest
import respx

from markproof.config import DocumentProbeConfig, MediaProbeConfig
from markproof.probes.base import ProbeError
from markproof.probes.document import DocumentProbe
from markproof.probes.http import MAX_REDIRECTS, fetch, same_origin
from markproof.probes.media import MediaProbe

_A = "https://target.example.invalid"
_B = "https://attacker.example.invalid"

#: The header names that matter. `Authorization` is the one httpx protects on its
#: own; the other two are what Azure deployments actually send, and are exactly
#: the case relying on httpx would have missed.
HEADER_NAMES = ["Authorization", "api-key", "x-functions-key"]


class TestOrigin:
    def test_scheme_counts(self) -> None:
        """An https page whose manifest arrives over http has left the origin."""
        assert not same_origin("https://a.test/x", "http://a.test/x")

    def test_port_counts(self) -> None:
        assert not same_origin("https://a.test:8443/x", "https://a.test/x")

    def test_path_does_not(self) -> None:
        assert same_origin("https://a.test/x", "https://a.test/y/z")


class TestCredentialsDoNotCrossOrigins:
    @pytest.mark.parametrize("header", HEADER_NAMES)
    @respx.mock
    def test_a_cross_origin_redirect_drops_the_credential(self, header: str) -> None:
        respx.get(f"{_A}/go").mock(
            return_value=httpx.Response(302, headers={"location": f"{_B}/landed"})
        )
        landed = respx.get(f"{_B}/landed").mock(return_value=httpx.Response(200, content=b"ok"))

        with httpx.Client() as client:
            fetch(
                client,
                "GET",
                f"{_A}/go",
                headers={header: "SECRET"},
                sensitive=frozenset({header}),
            )

        sent = landed.calls[0].request.headers
        assert header not in sent, f"{header} reached the redirect target"
        assert "SECRET" not in str(sent), sent

    @pytest.mark.parametrize("header", HEADER_NAMES)
    @respx.mock
    def test_a_same_origin_redirect_keeps_it(self, header: str) -> None:
        """Trailing-slash and canonical-path redirects are ordinary; do not break them."""
        respx.get(f"{_A}/go").mock(
            return_value=httpx.Response(301, headers={"location": f"{_A}/here"})
        )
        landed = respx.get(f"{_A}/here").mock(return_value=httpx.Response(200, content=b"ok"))

        with httpx.Client() as client:
            fetch(
                client,
                "GET",
                f"{_A}/go",
                headers={header: "SECRET"},
                sensitive=frozenset({header}),
            )
        assert landed.calls[0].request.headers[header] == "SECRET"

    @respx.mock
    def test_a_scheme_downgrade_is_a_different_origin(self) -> None:
        respx.get(f"{_A}/go").mock(
            return_value=httpx.Response(
                302, headers={"location": "http://target.example.invalid/x"}
            )
        )
        landed = respx.get("http://target.example.invalid/x").mock(
            return_value=httpx.Response(200, content=b"ok")
        )
        with httpx.Client() as client:
            fetch(
                client,
                "GET",
                f"{_A}/go",
                headers={"api-key": "S"},
                sensitive=frozenset({"api-key"}),
            )
        assert "api-key" not in landed.calls[0].request.headers

    @respx.mock
    def test_a_post_body_does_not_follow_either(self) -> None:
        """The request body is as much the operator's as the header is."""
        respx.post(f"{_A}/gen").mock(
            return_value=httpx.Response(307, headers={"location": f"{_B}/gen"})
        )
        landed = respx.get(f"{_B}/gen").mock(return_value=httpx.Response(200, json={}))
        with httpx.Client() as client:
            fetch(
                client,
                "POST",
                f"{_A}/gen",
                headers={"api-key": "S"},
                sensitive=frozenset({"api-key"}),
                json_body={"prompt": "secret prompt"},
            )
        assert landed.calls[0].request.content in (b"", None)

    @respx.mock
    def test_a_redirect_loop_ends_as_an_error(self) -> None:
        respx.get(f"{_A}/loop").mock(
            return_value=httpx.Response(302, headers={"location": f"{_A}/loop"})
        )
        with (
            httpx.Client() as client,
            pytest.raises(ProbeError, match=f"more than {MAX_REDIRECTS}"),
        ):
            fetch(client, "GET", f"{_A}/loop")


class TestTheProbesUseIt:
    @respx.mock
    def test_the_media_probe_does_not_leak_on_a_redirect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MARKPROOF_TOKEN", "SECRET-AZURE-KEY")
        respx.post(f"{_A}/v1/images").mock(
            return_value=httpx.Response(307, headers={"location": f"{_B}/v1/images"})
        )
        landed = respx.get(f"{_B}/v1/images").mock(
            return_value=httpx.Response(200, json={"data": [{"url": f"{_B}/a.png"}]})
        )
        respx.get(f"{_B}/a.png").mock(
            return_value=httpx.Response(
                200, content=b"\x89PNG\r\n\x1a\n", headers={"content-type": "image/png"}
            )
        )
        probe = MediaProbe(
            MediaProbeConfig.model_validate(
                {
                    "id": "images",
                    "type": "media",
                    "url": f"{_A}/v1/images",
                    "auth": {"header": "api-key", "env": "MARKPROOF_TOKEN", "prefix": ""},
                }
            )
        )
        # The verdict is irrelevant here; the header is the point.
        with contextlib.suppress(ProbeError):
            probe.collect()
        assert landed.calls, "the redirect was not followed at all"
        assert "SECRET-AZURE-KEY" not in str(landed.calls[0].request.headers)

    @respx.mock
    def test_a_manifest_may_not_be_redirected_off_origin(self) -> None:
        """The origin check is worthless if a 302 can move the destination after it."""
        page = b"<!doctype html><html><head></head><body>x</body></html>"
        respx.get(f"{_A}/index.html").mock(
            return_value=httpx.Response(
                200,
                content=page,
                headers={"content-type": "text/html", "link": '</m.c2pa>; rel="c2pa-manifest"'},
            )
        )
        respx.get(f"{_A}/m.c2pa").mock(
            return_value=httpx.Response(302, headers={"location": f"{_B}/m.c2pa"})
        )
        elsewhere = respx.get(f"{_B}/m.c2pa").mock(
            return_value=httpx.Response(200, content=b"ATTACKER MANIFEST")
        )
        probe = DocumentProbe(
            DocumentProbeConfig.model_validate(
                {"id": "page", "type": "document", "url": f"{_A}/index.html"}
            )
        )
        with pytest.raises(ProbeError, match="different origin"):
            probe.collect()
        assert not elsewhere.calls, "the foreign manifest was fetched anyway"
