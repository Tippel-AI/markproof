<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0

DRAFT — not published. Check before publishing:
  - star counts in the opening (measured 31.08.2026 — re-measure if this goes
    out much later, and move the date with them)
  - the third-party links still resolve (checked 31.08.2026: all seven GitHub
    repositories linked below answer)
  - the version in the console transcript (report currently says 0.1.0.dev0)
-->

# Content marks don't survive delivery

Two numbers from GitHub say more about the state of content marking than any
position paper. On 31 August 2026, two of the most-starred tools whose stated
purpose is stripping AI watermarks and provenance metadata —
[watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover) and
[remove-ai-watermarks](https://github.com/wiltodelta/remove-ai-watermarks) —
held about 19,600 and 5,300 stars between them, and the first of the two
collected its share in three weeks. The official C2PA reference implementation,
[c2pa-rs](https://github.com/contentauth/c2pa-rs), held 410.

You can read that as a story about bad actors, and it is one. The duller half
interests me more. Someone determined to remove a mark will remove it, and no
verification tool stops that. Far more often the mark disappears with nobody
laying a hand on it — because marking is a property of the delivery chain, not a
checkbox in a config file.

## Marking is a pipeline property, not a switch

A C2PA manifest rides along as a chunk in the file. It survives no thumbnailer
that re-encodes, no image CDN that drops metadata, and no privacy step that
strips EXIF and takes with it everything it doesn't recognise. Your generator
signed correctly. Your user receives a bare JPEG that looks pixel-identical and
differs only in provenance.

A text watermark lives in the token sequence. It dies when someone swaps the
model, turns a sampling knob, or drops a rewriting layer in front of the response
to smooth the tone. Nobody switched the watermark off. It simply is not there any
more.

A disclosure notice lives in the frontend. It goes missing in a refactor, loses
an A/B test to a warmer greeting, or slides behind the first user message because
the widget only fetches the notice once the chat opens — which is technically the
same thing as no disclosure before the first interaction.

All three share the property that makes them worth tooling for: they fail
silently. Nothing crashes, no test goes red, no log line warns you. You find out
when somebody outside asks — an auditor, a regulator, a journalist.

## Why this belongs in CI

Article 50 of the EU AI Act has applied since 2 August 2026. Systems that were
already on the market have until **2 December 2026** to retrofit machine-readable
marking under Art. 50(2). That date is why this is urgent, but it is not why I
built the thing.

I built it because of the question that follows. When someone asks "how do you
know your images shipped with their manifests?", the honest answer in most teams
today is that the config says so and the vendor says so. A config file is a claim
about the system. A call to the running endpoint is a measurement of it. The
difference costs nothing until somebody asks, and then it is the entire
difference.

Which puts the check where every other regression already surfaces: in the
pipeline, behind an exit code you can gate a deployment on.

## What markproof does

markproof calls your running endpoint the way a user would and checks what
actually arrives. Three probes — HTTP chat, media, and an optional Playwright
probe against the rendered interface — feed a rulepack covering the
machine-decidable parts of Article 50: disclosure in the first response and on a
direct question, disclosure before the first input in the interface, a valid C2PA
manifest with the right source type, the declared text watermark, and a
perceivable deepfake label.

Here is a run against a deliberately non-conformant test endpoint:

```console
$ markproof run --config markproof.yaml --report-dir report/
  probing chat → http://127.0.0.1:8099/v1/chat/completions
  probing images → http://127.0.0.1:8099/v1/images/generations

  demo-bot · rulepack art50-eu-2026.07 (1.0.0)

Rule       Result  Probe   Detail
MPF-D-001  FAIL    chat    no AI disclosure found in the responses in scope
MPF-D-003  FAIL    chat    no AI disclosure found in the responses in scope
MPF-L-001  WARN    images  no deepfake label found in the perceivable text
MPF-M-001  FAIL    images  1 of 1 asset(s) failed: no C2PA manifest embedded in
                           the delivered bytes
MPF-T-001  SKIP    chat    18 tokens is below the 100 needed for a meaningful
                           score — the detector's confidence grows with length,
                           and a short sample would be noise dressed as a verdict

  3 fail · 1 warn · 1 skip
```

Four decisions I spent the longest on are visible in those six lines.

**No LLM sits in the evaluation path.** The same input produces the same verdict,
every time. A compliance tool that estimates only moves the uncertainty somewhere
you can no longer see it — you trade an unknown delivery chain for an unknown
judge. Where decidability runs out, for instance on whether a notice is worded
"clearly and distinguishably", markproof emits `WARN` with the citation attached,
never a guessed `PASS`.

**That `SKIP` is the rule working, not dodging.** A watermark is a statistical
property of the token sequence, and 18 tokens carry no signal worth a verdict.
The rule asks for 100. No answer beats a wrong one.

**A probe that could not run is a failure, not a skipped test.** "The endpoint
was unreachable" and "the endpoint is compliant" must never look alike in a
report. A pipeline that goes green because nothing could be checked is the worst
outcome this tool can produce, so those cases get their own identifier,
`MPF-X-001`, and they count as failures.

**The media check reads assertions, not presence.** The distinction sounds
academic and isn't. An image can carry an embedded, validly signed manifest whose
hash bindings hold — and declare a source type of `algorithmicMedia` rather than
`trainedAlgorithmicMedia`. Algorithmically produced, but not by a trained model.
Every "does this file have Content Credentials?" tool says yes here. Art. 50(2)
still is not satisfied. I gave the test endpoint a dedicated mode for this case,
because it is the one an assertion-level check catches and a presence check waves
through.

The text watermark is verified against the operator's own configuration. To show
that the detector reads the token sequence rather than the vocabulary, the test
endpoint draws marked and unmarked answers from the same lattice of
interchangeable phrasings: same length, same register, same enumerations,
differing only in which synonym landed in which slot. Measured, the marked
answers score a mean-g value between 0.75 and 0.85 and the unmarked ones between
0.49 and 0.53 — chance level. The rule draws its lines at 0.70 and 0.56; anything
landing in between counts as inconclusive, and the shipped rulepack treats that
as a failure. That is the conservative reading, and it has a reason: an operator
who declares that they watermark should clear the bar.

What comes out at the end is a report in canonical JSON per RFC 8785, signed with
Ed25519. Verifying it needs nothing but the file, a public key and the CLI:

```console
$ markproof verify-report report.json --key public.pem
  ✓ signature valid against the supplied public key
  demo-bot · art50-eu-2026.07 v1.0.0 · 2026-08-31T14:40:28+00:00
```

Flip a single `FAIL` to `PASS` inside the report and the same command answers
`✗ signature does not match the report contents`. That is the point. The report
exists to be shown to a third party, and evidence the subject can rewrite
afterwards is not evidence.

## What it cannot do

This belongs in the same article as the part above, not in a FAQ further down.

markproof is a **self-conformance test, not a detector**. Verifying a text
watermark needs the generation-side configuration — the keys *are* the watermark.
Whoever holds them can verify and also forge. So the tool proves that your own
marking survives your own chain. It cannot tell you whether some arbitrary text
came from an AI, and it will not try: universal detection is scientifically shaky
and, when it is wrong about a person, reputationally destructive.

The **trust list stays out of v1**. The media check validates presence, hash
bindings and the required assertions. Whether the signer appears on the official
Conformance Trust List is not something it answers; that is scheduled for v1.1.
Until then a `PASS` on `MPF-M-001` means "a manifest is present, it matches the
bytes, and it declares the right source type" — not "the signer is trustworthy".

**Prominence is not graded.** Whether a notice that exists is also clear and
distinguishable depends on position, contrast and how long it stays on screen.
None of that appears in extracted text. The rules concerned therefore report
`WARN` and attach the evidence — for the interface disclosure as much as for the
deepfake label. The label carries a second problem on top: deciding whether
content is a deepfake at all is a case-by-case weighing of resemblance and
audience that no string comparison performs.

**Coverage is deliberately partial.** Two obligations sit in the rulepack as
reserved identifiers and are not implemented: disclosing on whose behalf an agent
acts, and the Art. 50(3) notice for emotion recognition. The second is not a
tooling gap — whether such a system is in operation is a fact about the
deployment that no response reveals. A documented hole beats a rule that always
passes.

And this is a technical conformance test, not legal advice. A green run is
evidence, not an opinion.

## What else is out there

The field is occupied, and for several jobs markproof is the wrong tool.

[art50-ci](https://github.com/Rubiss/art50-ci) drives a real browser against your
site and finds things an API probe cannot see in principle — obscured notices,
overlays, layout regressions. If your surface is a website, start there.
[provcheck](https://github.com/CreativeMayhemLtd/provcheck) verifies C2PA
locally, with neural watermark cross-checks, as a Rust CLI and a desktop app; for
files already on disk it is the better answer.
[c2patool](https://github.com/contentauth/c2patool) and the official
[c2pa-conformance-tool-cli](https://github.com/contentauth/c2pa-conformance-tool-cli)
answer "is this one asset validly signed?" — including against the trust list
that markproof does not yet carry. The media check here builds on `c2pa-python`
and replaces none of them.

markproof sits alongside, not above. It differs in four ways: it queries the
running API endpoint rather than a rendered page or a local file; it evaluates
Article 50 semantics at the assertion level rather than checking that a manifest
exists; it verifies the text watermark end to end against the operator's own
config; and it is Python, which is where the teams retrofitting this work
actually live.

## What comes next

v1.1 brings trust-list evaluation, more API dialects, and pattern files for more
languages — today the rulepack covers German and English. Prominence I still owe
you; I have no proposal for checking it deterministically without claiming more
than was measured.

The code is Apache-2.0 and the rulepacks are CC-BY-4.0, so they stay usable
outside this tool. If you ship visibly generated content into the EU, point it at
your staging endpoint once. A green run interests me less than the case where the
tool asserts something untrue — that is what I would like to hear about.
