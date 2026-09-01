# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Redirect handling that does not hand the operator's credential to the target.

The problem this exists to remove
---------------------------------
Every probe attaches an operator-supplied auth header and then followed redirects
with ``follow_redirects=True``. httpx strips exactly one header on a cross-host
redirect — ``Authorization``. ``AuthConfig.header`` is configurable, and the two
most common real alternatives are not it: Azure OpenAI uses ``api-key`` and Azure
Functions uses ``x-functions-key``.

So the endpoint under test decided where markproof sent the operator's production
credential. Answer a probe with ``302 Location: https://attacker.example/`` and
the key arrives there. For a tool people are asked to point at their own live
systems, with their own production tokens, that is the worst defect it can have —
and worse than the marking failures it was built to catch, because those cost
compliance and this costs a credential.

The rule here
-------------
Redirects are followed, because a permanent redirect or an http→https upgrade is
ordinary and refusing them would make the tool hostile to use. But **every
operator-supplied header is dropped the moment the origin changes**, where origin
is scheme, host and port — not host alone. A downgrade from https to http is an
origin change like any other.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from markproof.probes.base import ProbeError

__all__ = ["MAX_REDIRECTS", "fetch", "is_internal_host", "same_origin"]

#: Enough for the redirect chains real deployments have (canonical host, trailing
#: slash, http→https), few enough that a loop ends as an error rather than a hang.
MAX_REDIRECTS = 5


def same_origin(a: str, b: str) -> bool:
    """Whether two URLs share scheme, host and port.

    Host alone is not enough: an https page whose manifest is fetched over http
    has left the origin, and treating that as "same" would let a network attacker
    supply the bytes that decide a provenance verdict.
    """
    left, right = urlparse(a), urlparse(b)
    return (left.scheme, left.hostname, left.port) == (right.scheme, right.hostname, right.port)


def fetch(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    sensitive: frozenset[str] | None = None,
    content: bytes | None = None,
    json_body: object = None,
    stay_on_origin: bool = False,
) -> httpx.Response:
    """Perform a request, following redirects without leaking credentials.

    Args:
        sensitive: Header names to drop as soon as the origin changes. Matched
            case-insensitively, because HTTP header names are.
        stay_on_origin: Refuse a redirect that leaves the origin instead of
            following it stripped. Used where the destination is part of the
            claim being checked — a provenance manifest that can be redirected
            elsewhere is a manifest an attacker chooses.

    Raises:
        ProbeError: on a redirect loop, a redirect without a usable ``Location``,
            or a cross-origin redirect when ``stay_on_origin`` is set.
    """
    drop = {name.lower() for name in (sensitive or frozenset())}
    current = url
    sending = dict(headers or {})

    for _ in range(MAX_REDIRECTS + 1):
        response = client.request(method, current, headers=sending, content=content, json=json_body)
        if not response.is_redirect:
            return response

        location = response.headers.get("location")
        if not location:
            raise ProbeError(f"{current}: HTTP {response.status_code} with no Location header")
        target = str(httpx.URL(current).join(location))

        if not same_origin(current, target):
            if stay_on_origin:
                raise ProbeError(
                    f"{current} redirects to {target}, which is a different origin. "
                    "Refusing to follow: whoever answers that request decides the verdict, "
                    "and a provenance claim that a redirect can move is not a claim."
                )
            # Past this point the operator's credential would be travelling to a
            # host the target chose. Drop it and keep going: the fetch is still
            # worth making, the secret is not worth spending on it.
            sending = {k: v for k, v in sending.items() if k.lower() not in drop}
            # A body is a POST payload, and re-sending it to a host the target
            # picked has the same problem. RFC 9110 turns 303 into GET anyway;
            # for the rest, follow as a GET without the body.
            content, json_body, method = None, None, "GET"

        current = target

    raise ProbeError(f"{url}: more than {MAX_REDIRECTS} redirects — refusing to follow further")


def is_internal_host(url: str) -> bool:
    """Whether a URL points at an address only the runner can reach.

    Loopback, link-local, private and reserved ranges. The one that matters is
    ``169.254.169.254``: on every major cloud that address answers with instance
    credentials, and a probed endpoint choosing the URLs markproof fetches is a
    server-side request forgery with a very good payload.

    Hostnames that are not literal addresses are left alone. Resolving them here
    would make the verdict depend on DNS at check time, and a resolver that
    answers differently on two runs is exactly what the determinism claim rules
    out — the defence for those belongs in the network the runner sits on.
    """
    import ipaddress

    host = urlparse(url).hostname
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )
