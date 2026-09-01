# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Document probe — fetch what the server sent, and find the manifest bound to it.

Why the bytes and not the page
------------------------------
A C2PA manifest binds to a document by hashing it. For formats that cannot carry
an embedded manifest — HTML is the one that matters — the manifest travels
alongside, and the document is pointed at it by an RFC 8288 ``Link:`` response
header or a ``<link rel="c2pa-manifest">`` element (C2PA 2.4 §A.7, §15.5.3.2).

So the thing under test is the response body exactly as delivered. The UI probe
cannot supply it: a browser normalises markup before anything is readable, so
what it reports is a projection of the document rather than the document. That
difference is the whole reason this probe exists, and it is also the point of the
check — a minifier, a CDN's HTML rewriting, or a template change invalidates the
binding while the page still renders perfectly, and nothing else notices.

What it deliberately does not do
--------------------------------
It does not follow a manifest URL to another host. A provenance claim that
depends on a third party being up is a claim that stops being checkable when they
are not, and the C2PA specification's own preference for external manifests does
not extend to letting them wander.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from markproof.config import DocumentProbeConfig
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

__all__ = ["DocumentProbe", "manifest_link_from_header", "manifest_link_from_html"]

#: The relation type C2PA registers for an external manifest.
_REL = "c2pa-manifest"

#: `Link: <url>; rel="c2pa-manifest"` — one entry of a comma-separated list.
#: Bounded pieces only: no nested quantifier, so matching stays linear.
_LINK_HEADER = re.compile(
    r"<(?P<url>[^>]{1,2048})>\s*;(?P<params>[^,]{0,512})",
)

#: `<link rel="c2pa-manifest" href="...">` in either attribute order.
_LINK_ELEMENT = re.compile(
    r"<link\b(?P<attrs>[^>]{0,1024})>",
    re.IGNORECASE,
)
_HREF = re.compile(r'href\s*=\s*["\']([^"\']{1,2048})["\']', re.IGNORECASE)
_REL_ATTR = re.compile(r'rel\s*=\s*["\']?([^"\'>\s]{1,64})', re.IGNORECASE)


def manifest_link_from_header(value: str) -> str | None:
    """The manifest URL advertised in a ``Link:`` header, if there is one.

    Preferred over the element where both are present: a header survives an HTML
    rewrite that would move or strip the element, and it needs no modification of
    the document body — which is what makes it the natural fit for a server that
    generates pages.
    """
    for match in _LINK_HEADER.finditer(value):
        params = match.group("params").lower()
        if re.search(rf'rel\s*=\s*"?{re.escape(_REL)}"?(\s|;|$)', params):
            return match.group("url").strip()
    return None


def manifest_link_from_html(body: str) -> str | None:
    """The manifest URL advertised by a ``<link>`` element, if there is one."""
    for element in _LINK_ELEMENT.finditer(body):
        attrs = element.group("attrs")
        rel = _REL_ATTR.search(attrs)
        if rel is None or rel.group(1).lower() != _REL:
            continue
        href = _HREF.search(attrs)
        if href is not None:
            return href.group(1).strip()
    return None


class DocumentProbe:
    """Fetches a document and whatever manifest is bound to it."""

    def __init__(self, config: DocumentProbeConfig) -> None:
        self.config = config
        self.probe_id = config.id
        self.probe_kind = ProbeKind.DOCUMENT

    def collect(self) -> Evidence:
        """Fetch the document, resolve its manifest, and record both.

        Raises:
            ProbeError: for any transport failure, a non-2xx status, or a body
                larger than ``max_bytes``. A document that could not be fetched is
                an operational finding, never a silent pass.
        """
        headers = {}
        if self.config.auth is not None:
            name, value = self.config.auth.resolve()
            headers[name] = value

        try:
            with httpx.Client(timeout=self.config.timeout_seconds, follow_redirects=True) as client:
                response = client.get(self.config.url, headers=headers)
                body = self._body_of(response)
                manifest, source = self._manifest_for(client, response, body)
        except ProbeError:
            raise
        except httpx.HTTPError as exc:
            raise ProbeError(f"{self.config.url}: could not be fetched — {exc}") from exc

        media_type = (
            (response.headers.get("content-type") or "application/octet-stream")
            .split(";")[0]
            .strip()
        )
        artifact = Artifact.of(
            body,
            artifact_id=f"{self.probe_id}-document",
            media_type=media_type or "application/octet-stream",
            source_url=str(response.url),
            sidecar_manifest=manifest,
            sidecar_source=source,
        )

        # The response body is the evidence, but it is not perceivable text: a
        # label check must not read markup and call it what a person sees.
        summary = f"{len(body)} byte(s) of {media_type}"
        turn = Turn(
            prompt_id=self.config.prompt_id,
            request=[],
            response=Message(role=Role.ASSISTANT, content=summary),
            response_sha256=sha256_hex(summary),
            status_code=response.status_code,
            artifacts=(artifact,),
        )
        return Evidence(
            probe_id=self.probe_id,
            probe_kind=self.probe_kind,
            target_name=self.config.id,
            lang=self.config.lang,
            turns=(turn,),
        )

    def _body_of(self, response: httpx.Response) -> bytes:
        if response.status_code >= 400:
            raise ProbeError(
                f"{self.config.url} returned HTTP {response.status_code} — "
                "an error page is not the document under test"
            )
        body = response.content
        if len(body) > self.config.max_bytes:
            raise ProbeError(
                f"{self.config.url}: {len(body)} bytes exceeds max_bytes "
                f"({self.config.max_bytes}); raise it deliberately if the document is really "
                "this large"
            )
        return body

    def _manifest_for(
        self, client: httpx.Client, response: httpx.Response, body: bytes
    ) -> tuple[bytes | None, str | None]:
        """Resolve the external manifest, header first, then the document."""
        target = manifest_link_from_header(response.headers.get("link", ""))
        source = "link-header" if target else None
        if target is None:
            # Decoding for the element scan only. The bytes handed to the checker
            # stay exactly as delivered — the binding covers those, not a
            # re-encoding of them.
            target = manifest_link_from_html(body.decode("utf-8", errors="replace"))
            source = "link-element" if target else None
        if target is None:
            return None, None

        url = urljoin(str(response.url), target)
        if urlparse(url).netloc != urlparse(str(response.url)).netloc:
            raise ProbeError(
                f"{self.config.url}: the manifest is hosted on another origin ({url}). "
                "Refusing to follow it — a provenance claim that depends on a third party "
                "being reachable stops being checkable when they are not."
            )
        try:
            manifest = client.get(url)
        except httpx.HTTPError as exc:
            raise ProbeError(f"{url}: the linked manifest could not be fetched — {exc}") from exc
        if manifest.status_code >= 400:
            raise ProbeError(
                f"{url}: the document advertises a manifest that answers HTTP "
                f"{manifest.status_code}. A dangling provenance link is worse than none: "
                "it reads as marked and verifies as nothing."
            )
        return manifest.content, source
