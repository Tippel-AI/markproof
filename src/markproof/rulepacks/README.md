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

## What ships here

`art50-eu-2026.07.yaml` — rulepack id `art50-eu-2026.07`, version `1.0.0`,
licence `CC-BY-4.0`. It carries the mandatory `attribution:` line, its three
sources with dates and URLs, and six rules:

| Rule | Article | Check | Applies to | Severity |
|---|---|---|---|---|
| `MPF-D-001` | 50(1) | `disclosure-pattern`, first response of a fresh conversation | `http-chat` | `fail` |
| `MPF-D-002` | 50(1), 50(5) | `disclosure-pattern`, before the first user message | `ui` | `warn` |
| `MPF-D-003` | 50(1) | `disclosure-pattern`, bound to the direct-question prompts | `http-chat` | `fail` |
| `MPF-M-001` | 50(2) | `c2pa-verify`, manifest validity plus AI source type | `media` | `fail` |
| `MPF-T-001` | 50(2) | `synthid-detect` against the operator's own watermark config | `http-chat` | `fail` |
| `MPF-L-001` | 50(4) | `label-presence`, category `deepfake` | `media`, `ui` | `warn` |

Two rule ids are reserved in the trailer of the file and deliberately carry no
rule: `MPF-D-004` (agents disclosing on whose behalf they act) needs a pattern
file that does not exist yet, and `MPF-L-002` (the Article 50(3) notice) cannot
be decided from a response at all — the patterns for it ship, the rule does not.
The reasoning for every rule, and for every obligation that stayed out, is in
[`docs/RULES_SOURCES.md`](https://github.com/Tippel-AI/markproof/blob/main/docs/RULES_SOURCES.md)
— not part of the wheel, hence the link.

`markproof rules list art50-eu-2026.07` lists the same rules from the installed
package — with their full titles, and the attribution line underneath.

## Rules for anything added here

- Every rulepack carries a mandatory `attribution:` line. That line is how the
  CC-BY obligation is discharged; the schema rejects a rulepack without it.
- Rules **paraphrase** the sources and cite clause or margin numbers
  (`guideline_ref: "Guidelines C(2026) 5054, §3.1.2 para 33"`). No verbatim
  paragraphs of the Guidelines or the Code of Practice go into the YAML — a
  single short quote with attribution is the ceiling.
- Rule ids follow `MPF-<lane>-<nnn>`: `D` disclosure, `M` media marking,
  `T` text marking, `L` labels, `X` infrastructure/reachability.
- A rule that cannot be decided deterministically is a `warn` rule with its
  evidence attached, never a `pass` that guesses.

## Writing your own rulepack

`rulepack:` in `markproof.yaml` takes either the id of a packaged rulepack or a
path to a file of your own, so a local pack needs no installation:

```yaml
rulepack: ./rules/house-rules.yaml
```

`markproof rules schema` prints the JSON Schema the loader validates against,
and `markproof rules list ./rules/house-rules.yaml` loads a file straight from
disk. One limit worth knowing before you start: the `patterns_file` and
`labels_file` a rule names are resolved inside the installed
`markproof/patterns/` directory, not relative to your rulepack — a local pack
can reuse the shipped pattern files, but shipping pattern files of its own means
adding them there (see `../patterns/README.md`).

A rulepack you write is yours, under whatever licence you give it. The files
shipped *here* are CC-BY-4.0 because of what they derive from — as are
`../patterns/`, `../prompts/` and `docs/`; `NOTICE` §1 lists the perimeter. If
you copy one of them as a starting point, the `attribution:` line and the
licence travel with it.
