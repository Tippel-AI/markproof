<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# GitHub Action

A thin composite action around the CLI — it installs `markproof`, runs it, and
uploads the report. No logic lives here that is not also reachable from the
command line.

Defaults follow Auflage A2: `formats: [json, summary]`, which needs no system
packages and therefore works on any runner, including minimal container images.
**PDF is an opt-in input, never the default.**

## Status

Empty. `action.yml` is an M4 deliverable.

- TODO(M4): `action.yml` (composite) — `uv tool install markproof`, run with
  the default formats, upload `report.json` as a workflow artifact, write the
  Markdown summary to `$GITHUB_STEP_SUMMARY`, propagate the exit code.
- TODO(M4): inputs for config path, rulepack, formats, `fail-on`.
- TODO(M4): portability test on a minimal container runner without `apt install` —
  JSON and summary must still be produced.
