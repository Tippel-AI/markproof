# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""C2PA manifest verification (Art. 50(2)) — the first half of the unique lane.

Single point of contact with ``c2pa-python`` (official CAI bindings for
c2pa-rs, pinned to ``0.37.*``). Everything the SDK exposes is wrapped here so
that the 0.x API churn touches exactly one module; a nightly canary job runs the
same suite against ``c2pa-python@latest`` as an early warning.

Verdict ladder:

1. manifest present?              -> otherwise FAIL
2. manifest validates (hash bindings intact, signature chain formally valid)?
3. required assertions satisfied, e.g.
   ``c2pa.actions.v2: digitalSourceType == trainedAlgorithmicMedia``?

v1 boundary, documented rather than papered over: trust-list evaluation ("is
this signer trustworthy?") is v1.1. v1 accepts self-signed chains when the rule
says ``trust: { allow_self_signed: true }``.

``c2patool`` is a development-only convenience for building fixtures. It is
never a runtime requirement for users.
"""

# TODO(M2): wrapper around the c2pa-python reader; manifest presence,
#           validation status, assertion matching, per-format support matrix.
