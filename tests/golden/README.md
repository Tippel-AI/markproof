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

## Status

Empty. Cases arrive with the milestones that produce them.

- TODO(M1): conformant bot; missing disclosure; disclosure only in EN on a DE interface.
- TODO(M2): the C2PA matrix (signed / unsigned / tampered / wrong assertion x PNG, JPEG, MP4, WAV).
- TODO(M3): SynthID watermarked / not_watermarked / uncertain / text below the token floor.
