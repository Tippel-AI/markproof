# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The document probe and MPF-M-002 — provenance for what cannot embed it.

C2PA binds a manifest to a document by hashing it. A format that cannot carry the
manifest inside — HTML above all — points at an external one through an RFC 8288
``Link:`` response header or a ``<link rel="c2pa-manifest">`` element
(C2PA 2.4 §A.7, §15.5.3.2).

The binding is a hash over the bytes the server sent, which is exactly why this is
worth checking rather than assuming: a minifier, an HTML-rewriting CDN or a
template change turns a valid provenance claim into an invalid one while the page
still renders perfectly. Nothing errors and no log line appears.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from markproof.checks.c2pa_verify import C2paOutcome, C2paResult, verify_media
from markproof.config import DocumentProbeConfig
from markproof.probes.base import ProbeError
from markproof.probes.document import (
    DocumentProbe,
    manifest_link_from_header,
    manifest_link_from_html,
)
from markproof.rules.schema import C2paVerifyCheck

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "documents"
_URL = "https://pages.example.invalid/index.html"
_MANIFEST_URL = "https://pages.example.invalid/index.html.c2pa"


def _fixture(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _probe(**overrides: object) -> DocumentProbe:
    return DocumentProbe(
        DocumentProbeConfig.model_validate(
            {"id": "page", "type": "document", "url": _URL, **overrides}
        )
    )


class TestFindingTheManifest:
    """Two ways a document can point at its manifest, and they are not equivalent."""

    def test_a_link_header(self) -> None:
        assert (
            manifest_link_from_header('<index.html.c2pa>; rel="c2pa-manifest"') == "index.html.c2pa"
        )

    def test_a_link_header_among_others(self) -> None:
        value = '</style.css>; rel=preload, <m.c2pa>; rel="c2pa-manifest", </next>; rel=next'
        assert manifest_link_from_header(value) == "m.c2pa"

    def test_an_unrelated_link_header_is_not_a_manifest(self) -> None:
        assert manifest_link_from_header("</style.css>; rel=preload") is None

    def test_a_link_element(self) -> None:
        html = '<head><link rel="c2pa-manifest" href="m.c2pa"></head>'
        assert manifest_link_from_html(html) == "m.c2pa"

    def test_attribute_order_does_not_matter(self) -> None:
        html = '<head><link href="m.c2pa" rel="c2pa-manifest"></head>'
        assert manifest_link_from_html(html) == "m.c2pa"

    def test_a_stylesheet_link_is_not_a_manifest(self) -> None:
        assert manifest_link_from_html('<link rel="stylesheet" href="a.css">') is None

    def test_unquoted_attributes_are_html5_and_must_be_found(self) -> None:
        """`removeAttributeQuotes` is a default in html-minifier.

        A quoted-only pattern reports a correctly bound page as unmarked, and
        MPF-M-002 is severity fail — so a compliant deployment goes red and the
        finding text asserts there was no link element in bytes that contain one.
        """
        assert manifest_link_from_html("<link rel=c2pa-manifest href=m.c2pa>") == "m.c2pa"
        assert manifest_link_from_header("<m.c2pa>; rel=c2pa-manifest") == "m.c2pa"

    def test_single_quotes_too(self) -> None:
        assert manifest_link_from_html("<link rel='c2pa-manifest' href='m.c2pa'>") == "m.c2pa"

    def test_rel_is_a_list_not_a_string(self) -> None:
        """RFC 8288 makes `rel` space-separated, so a document may declare both."""
        assert (
            manifest_link_from_html('<link href="m.c2pa" rel="preload c2pa-manifest">') == "m.c2pa"
        )
        assert manifest_link_from_header('<m.c2pa>; rel="preload c2pa-manifest"') == "m.c2pa"

    def test_a_rel_that_merely_contains_the_name_does_not_count(self) -> None:
        """`c2pa-manifest-index` is a different relation, not this one."""
        assert manifest_link_from_html('<link rel="c2pa-manifest-index" href="x">') is None

    def test_no_link_at_all(self) -> None:
        assert manifest_link_from_html("<html><body>nothing</body></html>") is None


class TestCollecting:
    @respx.mock
    def test_the_header_form(self) -> None:
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200,
                content=_fixture("signed-valid.html"),
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "link": '<index.html.c2pa>; rel="c2pa-manifest"',
                },
            )
        )
        respx.get(_MANIFEST_URL).mock(
            return_value=httpx.Response(200, content=_fixture("signed-valid.html.c2pa"))
        )
        artifact = _probe().collect().turns[0].artifacts[0]
        assert artifact.sidecar_source == "link-header"
        assert artifact.media_type == "text/html"
        assert artifact.data == _fixture("signed-valid.html"), "the delivered bytes must be intact"

    @respx.mock
    def test_the_element_form_when_there_is_no_header(self) -> None:
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200, content=_fixture("signed-valid.html"), headers={"content-type": "text/html"}
            )
        )
        respx.get(_MANIFEST_URL).mock(
            return_value=httpx.Response(200, content=_fixture("signed-valid.html.c2pa"))
        )
        artifact = _probe().collect().turns[0].artifacts[0]
        assert artifact.sidecar_source == "link-element"

    @respx.mock
    def test_a_document_with_no_manifest_still_produces_evidence(self) -> None:
        """ "Nothing found" is a finding, not a reason to abort."""
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200, content=_fixture("unsigned.html"), headers={"content-type": "text/html"}
            )
        )
        artifact = _probe().collect().turns[0].artifacts[0]
        assert artifact.sidecar_manifest is None
        assert artifact.sidecar_source is None

    @respx.mock
    def test_the_manifest_bytes_never_reach_the_report(self) -> None:
        """Evidence stays diffable; the digest is what ties a finding to the bytes."""
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200,
                content=_fixture("signed-valid.html"),
                headers={
                    "content-type": "text/html",
                    "link": '<index.html.c2pa>; rel="c2pa-manifest"',
                },
            )
        )
        respx.get(_MANIFEST_URL).mock(
            return_value=httpx.Response(200, content=_fixture("signed-valid.html.c2pa"))
        )
        dumped = _probe().collect().model_dump(mode="json")
        assert "sidecar_manifest" not in dumped["turns"][0]["artifacts"][0]
        assert dumped["turns"][0]["artifacts"][0]["sidecar_source"] == "link-header"


class TestRefusals:
    @respx.mock
    def test_a_manifest_on_another_origin_is_refused(self) -> None:
        """A provenance claim that depends on a third party is not self-contained."""
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200,
                content=_fixture("unsigned.html"),
                headers={
                    "content-type": "text/html",
                    "link": '<https://cdn.elsewhere.invalid/m.c2pa>; rel="c2pa-manifest"',
                },
            )
        )
        with pytest.raises(ProbeError, match="another origin"):
            _probe().collect()

    @respx.mock
    def test_a_dangling_manifest_link_is_worse_than_none(self) -> None:
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200,
                content=_fixture("signed-valid.html"),
                headers={
                    "content-type": "text/html",
                    "link": '<index.html.c2pa>; rel="c2pa-manifest"',
                },
            )
        )
        respx.get(_MANIFEST_URL).mock(return_value=httpx.Response(404))
        with pytest.raises(ProbeError, match="reads as marked and verifies as nothing"):
            _probe().collect()

    @respx.mock
    def test_an_error_page_is_not_the_document_under_test(self) -> None:
        respx.get(_URL).mock(return_value=httpx.Response(503, content=b"<h1>down</h1>"))
        with pytest.raises(ProbeError, match="HTTP 503"):
            _probe().collect()

    @respx.mock
    def test_an_oversized_body_is_refused_rather_than_hashed(self) -> None:
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200, content=b"x" * 5000, headers={"content-type": "text/html"}
            )
        )
        with pytest.raises(ProbeError, match="exceeds max_bytes"):
            _probe(max_bytes=1024).collect()


class TestTheVerdicts:
    """The four outcomes, through the real check against generated fixtures."""

    @staticmethod
    def _verify(document: str, manifest: str | None) -> C2paResult:
        return verify_media(
            _fixture(document),
            "text/html",
            C2paVerifyCheck(type="c2pa-verify"),
            artifact_id=document,
            sidecar_manifest=_fixture(manifest) if manifest else None,
        )

    def test_a_bound_manifest_with_an_ai_source_type_passes(self) -> None:
        result = self._verify("signed-valid.html", "signed-valid.html.c2pa")
        assert result.outcome is C2paOutcome.VERIFIED
        assert result.passed

    def test_four_edited_characters_break_the_binding(self) -> None:
        """`1932` became `1888` after signing. The page still renders perfectly.

        This is the whole reason the rule exists: a minifier or an HTML-rewriting
        CDN does the same thing, silently, to every page it touches.
        """
        result = self._verify("tampered.html", "signed-valid.html.c2pa")
        assert result.outcome is C2paOutcome.INVALID
        assert not result.passed

    def test_validly_signed_is_not_the_same_as_marked_as_ai(self) -> None:
        """The distinction Article 50(2) turns on, and the one presence checks miss."""
        result = self._verify("signed-wrong-type.html", "signed-wrong-type.html.c2pa")
        assert result.outcome is C2paOutcome.WRONG_SOURCE_TYPE
        assert "digitalCapture" in (result.source_type or "")

    def test_no_manifest_is_an_absence_not_an_unreadable_payload(self) -> None:
        """HTML cannot embed one, so "none found" is definite rather than inconclusive."""
        result = self._verify("unsigned.html", None)
        assert result.outcome is C2paOutcome.MANIFEST_MISSING
        assert "cannot carry an embedded manifest" in (result.detail or "")


class TestTheManifestFetchIsBounded:
    """The document had a size limit and the manifest did not."""

    @respx.mock
    def test_an_oversized_manifest_is_refused(self) -> None:
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200,
                content=_fixture("signed-valid.html"),
                headers={"content-type": "text/html"},
            )
        )
        respx.get(_MANIFEST_URL).mock(return_value=httpx.Response(200, content=b"x" * 5000))
        with pytest.raises(ProbeError, match="over max_bytes"):
            _probe(max_bytes=2048).collect()

    @respx.mock
    def test_an_empty_manifest_is_not_a_manifest(self) -> None:
        respx.get(_URL).mock(
            return_value=httpx.Response(
                200, content=_fixture("signed-valid.html"), headers={"content-type": "text/html"}
            )
        )
        respx.get(_MANIFEST_URL).mock(return_value=httpx.Response(204))
        with pytest.raises(ProbeError, match="HTTP 204"):
            _probe().collect()


class TestInertMarkupIsNotADeclaration:
    """A `<link>` a browser never acts on must not choose the verdict.

    Taking one from a comment or a script string lets anything that can put text
    on a page — a code sample, a user-supplied string, a stale commented-out
    header — point markproof at bytes of its choosing.
    """

    def test_a_link_in_a_comment_is_ignored(self) -> None:
        assert (
            manifest_link_from_html('<!-- <link rel="c2pa-manifest" href="evil.c2pa"> -->') is None
        )

    def test_a_link_in_a_script_string_is_ignored(self) -> None:
        body = '<script>var s = \'<link rel="c2pa-manifest" href="evil.c2pa">\';</script>'
        assert manifest_link_from_html(body) is None

    def test_a_real_link_after_a_comment_is_still_found(self) -> None:
        assert (
            manifest_link_from_html('<!-- unrelated --><link rel="c2pa-manifest" href="m.c2pa">')
            == "m.c2pa"
        )
