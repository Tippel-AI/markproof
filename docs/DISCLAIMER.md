<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0
-->

# Disclaimer

## Trademarks and affiliation

> markproof is not affiliated with, endorsed by, or sponsored by Google DeepMind
> (SynthID), Adobe / the Content Authenticity Initiative (C2PA), or the European
> Commission. All trademarks are the property of their respective owners.

> markproof performs technical conformance testing. It is not legal advice and
> produces no certification. A passing report is evidence that specific checks
> passed at a specific time — nothing more.

Both paragraphs stand word for word in the README, and the first one is also the
string both PDF renderers print (`TRADEMARK_NOTICE` in
`src/markproof/report/pdf_reportlab.py`). `NOTICE` §3 carries the same trademark
paragraph and a shortened form of the second. They are part of the release
checklist, not decoration: edit one and you edit all of them.

Third-party names appear in this project only descriptively, to say what the
tool verifies — "verifies C2PA manifests", "detects SynthID text watermarks".
Consequently:

- no third-party logo appears in this repository, the documentation site, the
  demo GIF or any social asset;
- no component, package or command of this project is named after a third-party
  mark (no `synthid-*`, no `c2pa-*`);
- the project, the distribution and the command are all simply `markproof`,
  maintained by Tippel.

## Not legal advice

markproof runs technical checks against an endpoint you operate and reports what
it found. It does not tell you whether you comply with the EU AI Act, whether
Article 50 applies to your system, or what to do about a finding. A green run is
evidence, not a legal opinion; a red run is a hint about a technical fact, not a
finding of infringement. For a legal assessment, talk to a lawyer.

The rules in the shipped rulepacks paraphrase the Commission's Guidelines of
20 July 2026 and the Code of Practice on Transparency of 10 June 2026, and cite
the clause they derive from. The authoritative wording is in those sources, and the
interpretation encoded here is ours, not the Commission's.

## Scope limits

Stated plainly, because a compliance tool that overstates its reach is worse
than none:

- **Self-conformance test, not a detector.** SynthID text detection needs the
  watermark configuration of the generator. markproof therefore proves that
  *your* marking survives end to end on *your* endpoint. It cannot tell you
  whether some arbitrary text was written by an AI.
- **Not a universal AI-text detector.** markproof deliberately stays out of that
  lane: it is probabilistic, scientifically shaky and reputationally
  destructive.
- **Not a notice generator.** Tools like `ai-transparency-notice-generator`,
  Disclo or DiscloseKit produce disclosure text. markproof checks whether such
  text actually reaches users in the running system.
- **Not a classification wizard.** Whether your system is high-risk is a
  question for the Commission's own Compliance Checker, not for this tool.
- **No LLM in the evaluation path.** No LLM judge, no heuristic score decides
  PASS or FAIL. Where determinism ends — for instance whether a disclosure is
  "clear and distinguishable" — markproof returns WARN with the evidence, never a
  guessed PASS.
- **Coverage is partial.** markproof checks the machine-verifiable parts of
  Article 50. Obligations that are not machine-verifiable are out of scope and
  are documented as such, not silently skipped.
- **v1 boundaries.** C2PA trust-list evaluation (is the signer trustworthy?) is
  not part of v1; v1 validates manifest presence, hash bindings and the required
  assertions. Deepfake and emotion labels are checked for presence, not for
  prominence.
- **Applicability is recorded, not decided.** The `applicability` block in
  `markproof.yaml` is the operator's own statement about which Article 50
  obligations bind the target. markproof writes it into the report and skips the
  rules it excludes; it does not verify the claim and has no view on whether it
  is right. Whether Article 50 applies to a given system, and whether the
  operator is provider or deployer for the purposes of a given paragraph, is a
  legal question. A report whose scope was declared too narrowly is a document
  about a narrow test, not a defence.
- **Text marking on a web page is checked in one place only.** For a rendered
  document markproof scores the region named by `content_selector` against the
  operator's watermark configuration, and nothing else. It does not look for a
  machine-readable marking convention in the HTML, because for generated *text*
  in a web document there is no established one to look for — unlike C2PA for
  media. Inventing a tag and reporting its absence as non-conformance would
  manufacture a standard rather than test against one.

## Warranty

markproof is distributed under the Apache License 2.0, without warranties or
conditions of any kind, express or implied. See `LICENSE`, sections 7 and 8.
