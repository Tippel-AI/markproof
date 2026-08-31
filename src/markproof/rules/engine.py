# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The rule evaluator: ``evaluate(rulepack, evidence) -> findings``.

A pure function. No I/O, no clock, no network, no LLM. Identical inputs must
produce byte-identical findings, which is what makes the signed report worth
signing — the determinism test runs each golden evidence file through the full
pipeline twice (signature and timestamp zeroed) and asserts byte equality.

Result values: PASS / FAIL / WARN / SKIP. Stable ordering; every FAIL references
at least one artefact hash; an unknown ``check.type`` is a hard config error
rather than a silent SKIP.
"""

# TODO(M1): evaluate(), applicability matching (applies_to vs. probe types),
#           stable sort, severity -> result mapping.
# TODO(M1): property tests for the invariants listed in DEVELOPMENT_PLAN §7.3.
