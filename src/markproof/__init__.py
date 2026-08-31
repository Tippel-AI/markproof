# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""markproof — deterministic CI checks for EU AI Act Article 50.

Distribution, console script and import package are all named ``markproof``.

Two lanes, in positioning order:

1. **Marking verification** (the unique part) — do the media a deployed endpoint
   returns carry a valid C2PA manifest (including
   ``digitalSourceType = trainedAlgorithmicMedia``), and is its text output
   provably SynthID-marked using the operator's own watermark config?
2. **Disclosure check** (table stakes) — does the chatbot reveal that it is an AI
   before the first interaction?

No LLM sits in the evaluation path. ``evaluate(rulepack, evidence)`` is a pure
function: identical inputs produce byte-identical findings. The primary artefact
is an RFC-8785-canonicalised, Ed25519-signed JSON report plus a CI exit code.

markproof is a **self-conformance test** run against the operator's own endpoint.
It is not a universal AI detector, and it is not legal advice.
See ``docs/DISCLAIMER.md``.
"""

# TODO(M0): expose __version__ via importlib.metadata("markproof").
# TODO(M1): re-export the stable public API surface once it exists.
