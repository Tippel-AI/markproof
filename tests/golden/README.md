<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Golden files

One directory per case, each holding `evidence.json` and `expected_report.json`.
Golden files are regenerated only via `--update-golden` and reviewed like code —
an unreviewed golden update silently redefines what "conformant" means.

"Deterministic" is tested here: each golden evidence file goes through the full
pipeline (evaluator plus report builder, signature and timestamp zeroed) twice,
and the JSON output has to be byte-identical.

## Cases

Written by `generate.py`; regenerate the reports with
`pytest -m determinism --update-golden` and read the diff before committing it.

| Case | What it pins |
|---|---|
| `chat-conformant` | disclosure on the opener and on direct questions → PASS |
| `chat-silent` | the regression this tool exists to catch → FAIL |
| `chat-near-miss` | wording that resembles a disclosure → WARN, never a guess |
| `media-marked` | valid manifest with an AI source type → PASS |
| `media-tampered` | a manifest that no longer validates against its bytes → FAIL |
| `media-wrong-source-type` | correctly signed and *not* marked as AI → FAIL |
| `multi-probe` | three probes, so finding order is observable at all |
| `probe-unreachable` | `MPF-X-001`, and the report stays loadable |
| `scope-declared-out` | declared-inapplicable rules skip with the claim on record |

`multi-probe` is not redundant. With a single probe, sorting by rule and sorting
by probe produce the same file, so every other case is blind to an ordering
regression — the probe ids there (`zeta-chat`, `alpha-images`, `mid-page`) are
chosen so the two orders differ.

## What the gate is worth

Six deliberate mutations of the evaluator were checked against it, and all six
are caught: downgrading FAIL to WARN, sorting by probe instead of rule, turning an
inconclusive disclosure into PASS, ignoring the applicability declaration,
accepting any C2PA source type, and dropping the attribution from a skip reason.

Still not covered here, and covered elsewhere: the process exit code, which five
tests in `test_integration.py` pin.

## Not yet cases

- SynthID watermarked / not_watermarked / uncertain — needs the optional stack, so
  these belong in the nightly run rather than the per-PR gate.
