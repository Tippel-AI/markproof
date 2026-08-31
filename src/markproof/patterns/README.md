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

## What ships here

**`disclosure.de-en.yaml`** — the Article 50(1) phrasings. 30 positive patterns,
fifteen per language, covering the families the Guidelines treat as equivalent:
"ich bin eine KI", "you are talking to a chatbot", "no human is answering here".
10 negative patterns, five per language, collect the wordings paragraph 38 calls
insufficient on their own — the generic "assistant", "virtual assistant",
"automated system", the blanket "this site uses AI", the bare technology name.
Read by `MPF-D-001`, `MPF-D-002` and `MPF-D-003`.

**`labels.de-en.yaml`** — the Article 50(4) deep fake labels and the
Article 50(3) notice for emotion recognition and biometric categorisation. Every
entry carries a `category`, and a rule names the category it wants, so a deep
fake rule can never be satisfied by an emotion-recognition notice. Per language:
12 positive deep fake patterns and 10 positive emotion-recognition patterns,
plus 5 and 2 negative ones. Read by `MPF-L-001`, which asks for
`category: deepfake`. **The `emotion-recognition` entries ship without a rule
that uses them** — whether such a system is in operation is a fact about the
deployment, not about a response, so no packaged rule may assume it. Write a
local rule against the UI probe if you know it is; the reasoning is in
`docs/RULES_SOURCES.md` §9.5.

Both files are `version: 1`, every entry is a `regex`, and every entry carries
its Guidelines reference in `note`. The head of each file states the matching
contract in full: text is NFKC-normalised, casefolded and whitespace-collapsed
before matching, a positive match wins outright, and negatives only take effect
when nothing positive matched — they downgrade a finding to "needs human review"
instead of failing it. A phrasing that must stay a hard FAIL — a bot claiming to
be human — therefore belongs in neither list.

## Rules for anything added here

- Entries are paraphrased phrasings, not copied normative text
  (see `../rulepacks/README.md`).
- Every entry carries a stable id (`de-01-selbstauskunft-ki`) so a finding can
  name the exact pattern that matched, and a `note` with the paragraph the
  phrasing rests on.
- Regexes avoid nested quantifiers and unbounded wildcards; every alternation is
  a list of literals, so matching stays linear in the length of the response. A
  pattern that can backtrack is a denial of service against the tool that runs
  it.
- `category` is an enum in `rules/schema.py`, not a free string. A new labelling
  duty needs a member there; reusing an existing category silently widens every
  rule that reads it.

## Adding your own

A rule finds its pattern file by name, resolved inside this directory of the
*installed* package — not relative to the rulepack. A local rulepack can
therefore reuse the files shipped here without any setup, but a pattern file of
your own has to live next to them (an editable install, or a fork, is the
straightforward way). That is a rough edge of the loader, not a decision worth
defending — if it blocks you, say so in an issue.
