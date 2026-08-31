# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Check implementations — the deterministic verdict per rule ``check.type``.

One module per check family:

``disclosure``    pattern matching against curated DE/EN phrasings
``c2pa_verify``   C2PA manifest validation via the official CAI bindings
``synthid``       SynthID text watermark detection (extra ``[synthid]``)
``labels``        deepfake / emotion-recognition label presence

Rules: no LLM, no heuristic score decides PASS/FAIL. Where determinism ends,
a check returns WARN with the evidence attached — never a guessed PASS.
"""

# TODO(M1): dispatch table check.type -> callable, unknown type => hard config error.
