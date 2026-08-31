<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Negative battery

The cases where a compliance tool is allowed to fail loudly and forbidden to
fail quietly.

## Status

Empty. Cases arrive with the milestones that produce them.

- TODO(M2): tampered media (byte flips at ten positions), stripped metadata.
- TODO(M3): `detector: bayesian` without `detector_model:` -> hard config error,
  never a silent fallback to `mean-g`.
- TODO(M4): a manipulated `report.json` must fail `markproof verify-report`.
- TODO(M5): endpoint returns HTML instead of JSON; 401 / 429 / timeout / TLS error
  -> finding `MPF-X-001`, FAIL rather than a traceback.
- TODO(M1): rulepack with an unknown `check.type` -> hard config error, not a silent SKIP.
