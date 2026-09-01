<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Negative battery

The cases where a compliance tool is allowed to fail loudly and forbidden to
fail quietly.

## Status

**Not a separate directory of fixtures.** The cases this file once listed as TODO
all exist, and they live with the code they exercise rather than here:

| Case | Where |
|---|---|
| tampered media, stripped metadata | `tests/fixtures/media/` + `tests/test_c2pa_verify.py` |
| tampered document against its manifest | `tests/fixtures/documents/` + `tests/golden/document-rewritten/` |
| `detector: bayesian` without a model | `tests/test_synthid.py` |
| a manipulated `report.json` fails `verify-report` | `tests/test_cli.py::TestVerifyReport` |
| HTML instead of JSON, 401/429/timeout/TLS | `tests/test_hardening.py` |
| a rulepack with an unknown `check.type` | `tests/test_engine.py::TestFailureModes` |
| a credential surviving a cross-origin redirect | `tests/test_redirects.py` |

Kept as a pointer rather than deleted, because "where are the negative tests"
is a fair question to ask of a compliance tool and the answer should not be
"grep for it".
