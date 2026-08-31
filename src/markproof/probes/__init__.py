# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Probe engine — collects evidence, never judges it.

Probes talk to the deployed endpoint and record what came back: request/response
pairs, raw media bytes, headers, screenshots, each with a SHA-256 digest. All
grading happens later in ``markproof.checks`` and ``markproof.rules``.

This is the only non-deterministic layer in markproof (network, model sampling).
Tests replace it with recorded fixtures so the rest of the pipeline stays
byte-reproducible.
"""

# TODO(M1): register the probe types declared in markproof.yaml.
