# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""RFC 8785 canonicalisation plus Ed25519 signing and verification.

Canonicalisation uses the ``rfc8785`` package (Trail of Bits, Apache-2.0, pure
Python, no dependencies), pinned exactly — JCS bugs are subtle and here they are
signature-relevant, so this is not a place for a hand-rolled ~100-line
canonicaliser. JCS itself is a frozen spec, so a pinned old version is fine.

Signing uses ``cryptography`` (Ed25519). The private key comes from an
environment variable or a file, never from the config file or the repo.
``markproof verify-report`` re-canonicalises a report and checks its signature
against a public key — the auditor path, deliberately usable without running any
probe.
"""

# TODO(M4): canonicalise(), sign(), verify(); keygen helper.
# TODO(M4): negative test — a one-byte edit to report.json must fail verification.
