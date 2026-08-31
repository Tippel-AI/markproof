<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0
-->

# Patterns

Curated phrasings used by the disclosure and label checks, shipped as package
data. **Licensed CC-BY-4.0**, not Apache-2.0 — see `LICENSE-DATA` and `NOTICE`
in the repository root.

Patterns are matched as regexes and normalised substrings (Unicode-normalised,
case-insensitive). There is no fuzzy score: a pattern matches or it does not.
Anything the patterns cannot settle becomes a WARN with the evidence attached.

## Status

Empty. The pattern files are M1/M5 deliverables.

- TODO(M1): `disclosure.de-en.yaml` — AI-disclosure phrasings, DE and EN, each
  entry with a stable id (`disclosure.de.v1#7`) so findings can cite the exact
  pattern that matched.
- TODO(M5): `deepfake-labels.yaml` (Art. 50(4)).
- TODO(M5): `emotion-labels.yaml` (Art. 50(3)).

Every entry carries its Guidelines reference. Entries are paraphrased phrasings,
not copied normative text (see `../rulepacks/README.md`).
