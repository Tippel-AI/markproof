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
- the project, the distribution, the command and the rulepack namespace are all
  simply `markproof` / `MPF-*`, maintained by Tippel — no third-party mark is used
  as a product name, a package name or branding;
- the marks do appear inside the code where they describe what it does: the module
  `markproof.checks.synthid`, the module `markproof.checks.c2pa_verify`, the
  optional extra `[synthid]` and the rulepack check type `c2pa-verify`. That is
  nominative use — naming the technology being verified — and it is deliberate:
  calling the SynthID check something else would make the code harder to read and
  the claim harder to check. It is not an endorsement, an affiliation, or a claim
  to the marks.

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
- **Evidence can contain personal data.** Probes record what an endpoint returned,
  verbatim, and a report records the URLs probed. If a target's response includes
  personal data — a name in a chat reply, an identifier in an error — it lands in
  the evidence and, where a report is signed and shared, travels with it. markproof
  does not inspect, redact or classify what it records. Point it at a test target,
  or read what you are about to hand over.
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
  operator's watermark configuration, and nothing else — a `ui` probe reports what
  a browser rendered, which is not the bytes a C2PA manifest signs.
- **Document provenance is a separate probe.** `MPF-M-002` verifies the C2PA
  binding for a delivered document (C2PA Technical Specification 2.4, §A.7) via
  the `document` probe, which fetches the bytes the server sent and resolves the
  manifest from a `Link:` header or a `<link rel="c2pa-manifest">` element. It
  refuses a manifest hosted on another origin: a provenance claim that depends on
  a third party being reachable stops being checkable when they are not.
- **Marking is checked, detectability is not.** Article 50(2) requires that
  outputs be marked *and* detectable as artificially generated. markproof
  measures the first limb against your own configuration. Whether a third party
  who does not hold your watermark keys can detect the mark is a property of the
  ecosystem, not of your endpoint, and no probe run against your system can
  establish it.

## Warranty

markproof is distributed under the Apache License 2.0, without warranties or
conditions of any kind, express or implied. See `LICENSE`, sections 7 and 8.
