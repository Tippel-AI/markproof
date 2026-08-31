<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0
-->

# Rulepacks

Versioned YAML rulepacks, shipped as package data. **Licensed CC-BY-4.0**, not
Apache-2.0 — see `LICENSE-DATA` and `NOTICE` in the repository root. They are
derived from Commission material that is itself CC-BY-4.0, and keeping them
separately licensed keeps the attribution chain clean and lets others reuse the
rulepacks on their own terms.

## Rules for anything added here

- Every rulepack carries a mandatory `attribution:` line. That line is how the
  CC-BY obligation is discharged; the schema rejects a rulepack without it.
- Rules **paraphrase** the sources and cite clause or margin numbers
  (`guideline_ref: "Guidelines §3.2 Rn. 41"`). No verbatim paragraphs of the
  Guidelines or the Code of Practice go into the YAML — a single short quote
  with attribution is the ceiling.
- Rule ids follow `MPF-<lane>-<nnn>`: `D` disclosure, `M` media marking,
  `T` text marking, `L` labels, `X` infrastructure/reachability.

## Status

Empty. The first rulepack is an M1 deliverable.

- TODO(M1): `art50-eu-2026.07.yaml` — D rules first (disclosure), with real
  clause references from the Guidelines of 20.07.2026 and the attribution line.
- TODO(M1): carry over the exact `C(2026)` reference number from the Guidelines PDF.
- TODO(M2): add the M rules (C2PA), paraphrased from the Code of Practice commitments.
- TODO(M3): add the T rules (SynthID / text metadata) — legally the most delicate
  ones, so the paraphrased clause reference is mandatory before they ship.
