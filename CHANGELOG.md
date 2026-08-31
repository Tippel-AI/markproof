<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Changelog

Everything worth knowing about a released version of markproof is recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Two surfaces carry compatibility weight, so any movement in them is called out
explicitly: the **rulepack format** — what a rulepack file may contain — and the
**report schema** — what `report.json` looks like, and therefore what a future
`markproof verify-report` will still accept. Both are still settling before 1.0.

## [Unreleased]

_Nothing yet._

## [0.1.0] - unreleased

The first public release. Until now you could describe your Article 50 setup; from
here you can measure it against the system your users actually reach, and hand
someone else the measurement.

### Added

- **Probe a running endpoint, not a configuration file.** `markproof run --config
  markproof.yaml` calls your deployed system the way a user would and judges what
  comes back. Three probe types cover the surfaces where marks get lost: an HTTP
  chat endpoint (`openai-chat` and `generic-json` wire shapes), a media endpoint
  whose returned URLs are followed and whose inline base64 is decoded, and — behind
  the `[ui]` extra — a rendered widget driven by Playwright. Each prompt goes out as
  a fresh conversation, because Article 50(1) is a claim about the *first* exchange
  and a reused session cannot observe it.

- **Verify that delivered media still carry their C2PA manifest** (`MPF-M-001`,
  Art. 50(2)). markproof reads the bytes your endpoint served, not the ones your
  generator signed, and requires a valid manifest asserting `digitalSourceType =
  trainedAlgorithmicMedia`. The verdict ladder keeps apart what a summary would
  blur: a stripped manifest, an invalid one, an unreadable payload and a manifest
  that marks the asset as the wrong kind of thing are four different findings with
  four different fixes. Remote manifests are refused by default — one a CDN can drop
  is the regression this check exists to catch. One bad asset out of ten fails the
  finding; nine marked images is a delivery regression that reaches real users, not
  90 % compliance.

- **Verify that generated text still carries your watermark** (`MPF-T-001`,
  Art. 50(2)). Behind the `[synthid]` extra, the SynthID `mean-g` detector scores
  the response against your own watermark configuration — no detector model to
  train, no language model in the loop, only the tokenizer and your config. The
  verdict has three states, not two: `watermarked`, `not_watermarked`, and an
  explicit `uncertain` band between the thresholds (defaults 0.56 and 0.70, measured
  rather than estimated). Text shorter than the token floor (default 100) is skipped
  with a reason instead of scored, because a short sample is noise dressed as a
  verdict.

- **Check that the bot says it is a bot** (`MPF-D-001`, `MPF-D-003`, Art. 50(1)),
  in the opening response of a fresh conversation and again when asked directly.
  Matching runs on NFKC-normalised, case-folded text against curated positive and
  negative phrasings in German and English, and resolves four ways: disclosed, not
  disclosed, near miss ("I am your assistant" is not a disclosure), and late. A
  timing bug and a missing feature get different names because they need different
  fixes.

- **Check that a rendered interface discloses before the user types anything**
  (`MPF-D-002`, Art. 50(1)/(5)). The UI probe loads the widget, captures the state
  ahead of the first input, and attaches the screenshot as evidence. Severity is
  `warn`: the wording being present is decidable, its prominence is not.

- **Check for deepfake and emotion-recognition labels** (`MPF-L-001`, Art. 50(4))
  in what a person actually reads, on both media and UI surfaces. Also `warn`, and
  for a stated reason — see the limits below.

- **A probe that could not run is a finding, never a green build** (`MPF-X-001`).
  An unreachable endpoint, a timeout, a TLS failure, a 401 or a 429 becomes a FAIL
  with the transport error attached, and the run continues so that the probes which
  did succeed still report. "The endpoint was unreachable" and "the endpoint is
  compliant" are opposite results, and the report now says which one happened.

- **Hand the result to someone who does not trust you.** Every run can write an
  RFC 8785-canonicalised, Ed25519-signed `report.json` alongside a Markdown summary
  that leads with the failures and their guideline citations. `markproof
  verify-report report.json --key public.pem` checks it offline, on a machine that
  never saw the system under test. Without `--key` it verifies against the embedded
  key and says plainly that this proves integrity, not identity. `markproof keygen`
  writes the key pair, the private half owner-readable only, and loading a
  group- or world-readable private key is refused.

- **Byte-identical output for identical evidence.** No LLM sits in the evaluation
  path, `evaluate()` is pure, and with the timestamp pinned two runs produce the
  same bytes down to the signature. The exact canonicalisation library version
  travels inside the signature block so the signed bytes stay reproducible years
  from now.

- **Gate a pipeline on it.** The composite GitHub Action in `action/` installs
  markproof, runs the check, writes the job summary and uploads the report — the
  summary and the upload happen even when the check fails, since a failed check
  whose evidence is lost is worth nothing. `fail-on` chooses whether WARN goes red;
  by default only FAIL does. Exit codes separate the two kinds of bad news: `1` is a
  verdict about the system under test, `2` means markproof itself could not be used
  (unusable config, unreadable key). An operator mistake writes no report; a failed
  probe writes one, because proof that the check ran beats no file at all.

- **Read and reuse the rules.** The shipped rulepack `art50-eu-2026.07` cites the
  Commission Guidelines paragraph behind every rule and is published under
  CC-BY-4.0, so it can be used outside this tool. `markproof rules list
  art50-eu-2026.07` prints it; `markproof rules schema` exports the JSON Schema.
  `docs/RULES_SOURCES.md` records the reasoning, including the obligations that were
  deliberately left unimplemented.

- **Optional PDF output.** `[pdf]` renders with reportlab in pure Python and needs
  no system packages; `[pdf-html]` uses WeasyPrint for a nicer HTML-templated
  document and fails with a clear message when Pango or cairo are missing rather
  than quietly producing a different document than the one you asked for. The signed
  JSON stays the authoritative evidence — a PDF carries a creation time and a
  document id and is therefore not byte-reproducible.

- Python 3.11, 3.12 and 3.13. The default install path pulls no system
  dependencies; every heavy component (torch, Playwright, WeasyPrint) sits behind an
  extra you have to ask for.

### Known limits

These are boundaries of the release, not bugs, and they are stated here so nobody
has to discover them from a passing report.

- **C2PA trust-list evaluation is not in this version.** `MPF-M-001` establishes
  that a manifest is present, structurally valid, correctly hash-bound and carries
  the required assertions. It does not ask whether the *signer* belongs to the
  official C2PA Conformance Trust List, so a manifest signed by an unknown or
  self-signed issuer passes. Signer trust is planned for v1.1; until then, use
  `c2patool` or the CAI conformance CLI for that question.

- **The `bayesian` SynthID detector needs a model you have trained.** Only
  `mean-g` ships working out of the box, and it is the default precisely because it
  needs nothing but your watermark configuration. Selecting `detector: bayesian`
  without an operator-trained `BayesianDetectorModel` reports itself as unsupported,
  with the reason, instead of silently falling back to a different detector and
  handing you a verdict from a check you did not request.

- **Label prominence is not assessed.** `MPF-L-001` asks whether the wording is
  there and stops. Whether the content is a deep fake at all is a case-by-case
  judgement about audience and context, and whether a label that exists is *clear
  and distinguishable* depends on position, contrast, size and duration — none of
  which are in the text. Both are why the rule warns instead of failing: a PASS
  would claim a precision the check does not have.

- More generally: markproof is a self-conformance test against your own endpoint.
  It is **not** a universal AI-text detector, it marks and signs nothing itself, and
  it is not legal advice. A passing report says that specific checks passed at a
  specific time. See `docs/DISCLAIMER.md`.

[Unreleased]: https://github.com/Tippel-AI/markproof/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Tippel-AI/markproof/releases/tag/v0.1.0
