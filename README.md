<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# markproof

**Your model marks its output. Your CDN doesn't care.**

markproof calls your *running* AI endpoint the way a user would, and checks what actually arrives: is the image still carrying its C2PA manifest, is the text still watermarked, does the bot say it's a bot? Deterministic pass/fail, a signed evidence report, and an exit code your pipeline can gate on.

```bash
pipx install git+https://github.com/Tippel-AI/markproof
markproof run --config markproof.yaml
```

> **Status: unreleased.** Not on PyPI yet, so install from git as above. Every check
> in the table below runs against a live endpoint and is covered by tests, but the
> rulepack format and the report schema will still change before 1.0 — treat a
> report produced today as evidence about today, not as a stable artefact. The
> first tagged release, `pipx install markproof`, and a versioned action reference
> land together ([#1](https://github.com/Tippel-AI/markproof/issues/1)).

---

## Why this exists

Content marking is not a setting you switch on. It is a property that has to survive an entire delivery chain — and it usually doesn't:

- A **C2PA manifest** rarely survives a resize, a re-encode, or a metadata-stripping image CDN. Your generator signed correctly; your user receives a bare JPEG.
- A **text watermark** disappears when someone swaps the model, changes sampling parameters, or puts a rewriting layer in front of the response.
- A **disclosure notice** vanishes when the frontend gets refactored, an A/B test replaces the greeting, or the notice only renders *after* the first user message.

All three fail **silently**. Nothing crashes, no test goes red, no log line warns you. You find out when someone from outside asks — an auditor, a regulator, a journalist.

If you want a sense of how fragile these marks are in the wild, look at where the attention went. On **31 August 2026**, two of the most-starred tools whose stated purpose is stripping AI watermarks and provenance metadata — [watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover) and [remove-ai-watermarks](https://github.com/wiltodelta/remove-ai-watermarks) — held about **19,600** and **5,300** GitHub stars; the first collected them in its first three weeks. The official C2PA reference implementation, [c2pa-rs](https://github.com/contentauth/c2pa-rs), held **410**. Star counts move, so check them rather than trust this line. Marks get stripped deliberately, and far more often by accident.

There is also a paperwork problem. Even a team doing everything right cannot currently *show* it. Asked "how do you know your images shipped with their manifests?", the honest answer today is a config file and a vendor's word. markproof turns that into a measurement with a timestamp and a signature.

## What it checks

| Rule | What it measures | Surface | AI Act |
|---|---|---|---|
| `MPF-D-001` | Does the first response state that the counterpart is an AI? | chat | Art. 50(1) |
| `MPF-D-002` | Does the interface disclose **before** the user types anything? | UI | Art. 50(1) |
| `MPF-D-003` | Is a direct question ("are you human?") answered truthfully? | chat | Art. 50(1) |
| `MPF-M-001` | Do delivered media carry a valid C2PA manifest declaring an AI source type? | media | Art. 50(2) |
| `MPF-T-001` | Is the text provably watermarked, against *your* config? | chat, page | Art. 50(2) |
| `MPF-L-001` | Is a deepfake label present? (warns — presence only, not prominence) | media, UI | Art. 50(4) |
| `MPF-X-001` | Recorded when a probe could not run at all — never a silent pass. | any | — |

Every rule names the obligation it serves, and **you say which obligations bind you**:

```yaml
applicability:
  ai-interaction: false        # no chatbot — Art. 50(1) does not arise
  deepfake-labelling: false    # no deep fakes generated
  synthetic-text-marking: true # the page copy is model-written
```

Rules for an obligation you declare away are skipped and *named* as skipped, not
quietly dropped. Without this block everything runs, so silence never removes a
check.

This is not a mute switch, and the difference is the point. Declaring an
obligation inapplicable puts a claim into the **signed** report: a green run that
skipped the deep fake rule now says, over your own key, that you declared no deep
fakes. And the claim binds you the other way too — declare an obligation
applicable and give markproof nothing to check it with, and you get a warning
instead of a silent skip. "We mark our text", "nothing was checked" and a green
build is exactly the failure this tool exists to remove.

The three rules with a **UI** or **page** surface drive a real browser, so they need
the optional extra and its browser binaries — `pipx install "markproof[ui]"` followed
by `playwright install chromium`. The base install covers everything else.

**No LLM sits in the evaluation path.** Same inputs, same verdict, every time. Where determinism ends — for instance, whether a disclosure is worded "clearly and distinguishably" — markproof emits `WARN` with the guideline citation, never a guessed `PASS`. A compliance tool that estimates just moves the problem somewhere you can't see it.

## Example

```yaml
# markproof.yaml
version: 1
target:
  name: support-bot prod
  probes:
    - id: chat
      type: http-chat
      url: https://api.example.com/v1/chat/completions
      auth: { header: Authorization, env: MARKPROOF_TOKEN }
    - id: images
      type: media
      url: https://api.example.com/v1/images/generations
      response_format: url          # or b64_json
    - id: article
      type: ui
      url: https://example.com/blog/latest
      content_selector: "article .body"   # the model-written text, nothing else
applicability:
  deepfake-labelling: false       # this target generates no deep fakes
text_marking:
  method: synthid
  watermark_config: secrets/watermark_config.json   # never commit this
rulepack: art50-eu-2026.07
```

```console
$ cd examples/demo-bot && DEMO_MODE=fail uvicorn app:app --port 8099 &
$ markproof run --config markproof.yaml --report-dir markproof-report

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
                           and a short sample would be noise dressed as a
                           verdict

  3 fail · 1 warn · 1 skip

  report written to markproof-report/report.json
  summary written to markproof-report/summary.md
  unsigned — set MARKPROOF_SIGNING_KEY to produce verifiable evidence

$ echo $?
1
```

That is captured output, not a mock-up, and you can reproduce it: [`examples/demo-bot`](examples/demo-bot) is a deliberately non-conformant FastAPI bot with four modes. Run it with `DEMO_MODE=pass` and the same command exits 0.

Two things worth noticing. `MPF-T-001` **skips** rather than guessing: an 18-token reply cannot carry a watermark score worth reporting, and saying so is the honest answer. `MPF-L-001` **warns** rather than failing, because whether content is a deep fake at all is a judgement no pattern match can make.

The report is canonical JSON (RFC 8785) with an Ed25519 signature. Anyone can re-verify it offline, without access to your systems:

```bash
markproof verify-report report.json --key public.pem
```

## Use in CI

```yaml
- uses: Tippel-AI/markproof/action@main   # a versioned tag follows the first release
  with:
    config: markproof.yaml
    extras: synthid        # only if you verify text marking
                           # add `ui` for the rendered-interface rules
  env:
    MARKPROOF_TOKEN: ${{ secrets.API_TOKEN }}
    MARKPROOF_SIGNING_KEY: ${{ secrets.MARKPROOF_SIGNING_KEY }}
```

The default output is signed JSON plus a job summary — no system dependencies, so
that path works on any runner. A PDF for the auditor is opt-in through the config:

```yaml
report:
  formats: [json, summary, pdf]     # needs: pipx install "markproof[pdf]"
```

`pdf` is pure Python. `pdf-html` renders through WeasyPrint and wants Pango and
cairo, which pip does not install — so it is never on the default path.

## Related projects

markproof is not the only tool in this space, and for several jobs it isn't the right one:

- **[art50-ci](https://github.com/Rubiss/art50-ci)** — a GitHub Marketplace action (TypeScript/Playwright) that drives a *browser* against your site: disclosure regressions, overlay obstruction, and C2PA source-to-delivery label tracing, with JSON/HTML/screenshot artefacts. If your surface is a website, look here first.
- **[provcheck](https://github.com/CreativeMayhemLtd/provcheck)** — a local-first C2PA verifier with neural watermark cross-checks (Rust, CLI + desktop GUI). Best choice for inspecting *files* you already have on disk.
- **[c2patool](https://github.com/contentauth/c2patool)** and **[c2pa-conformance-tool-cli](https://github.com/contentauth/c2pa-conformance-tool-cli)** — the official CAI tooling, including validation against the official Conformance Trust List. If your question is "is this one asset validly signed?", use these; markproof's media check builds on `c2pa-python` and does not replace them.
- **[AIMark-Sidecar](https://github.com/MMVFIRM/AIMark-Sidecar)** — sits on the *producing* side: applies marks and issues signed receipts. Complementary to markproof, and a good test target.

**Where markproof differs:** it queries the running API endpoint rather than a rendered page or a local file, it evaluates Article 50 semantics at the assertion level (not just "is a manifest present"), it verifies SynthID text end-to-end against your own watermark config, and it lives in Python — where the teams retrofitting this work actually are.

## What it is not

- **Not an AI text detector.** markproof cannot tell you whether arbitrary text came from an AI. It tests *your* system against *your* watermark configuration. Universal detection is scientifically unreliable and we won't pretend otherwise.
- **Not a marker.** It signs and watermarks nothing. Tools that apply marks are neighbours, not competitors.
- **Not a notice generator.** Writing disclosure copy is a solved problem elsewhere; markproof checks whether the copy survives to production.
- **Not a compliance wizard.** "Am I high-risk?" is answered by the Commission's own Compliance Checker in 24 languages.
- **No dashboard, no SaaS, no server.** CLI and CI, offline-capable, air-gap friendly.
- **Not legal advice.** A technical conformance test, nothing more.
- **Not complete coverage of Article 50.** Emotion-recognition disclosure
  (Art. 50(3)) is not checked: deciding whether a system performs emotion
  recognition at all is out of reach for a probe that only sees its output.
  Label *prominence* is not judged either — only whether the wording is there.
- **Not a judge of whether an obligation applies to you.** `applicability` records
  *your* answer; it does not compute one. Whether Article 50 binds a given system,
  and as provider or as deployer, is a legal question this tool has no view on.
- **Not yet checking the C2PA marking of web pages.** On a rendered page
  markproof checks one thing today: whether the region you name still carries
  the watermark you configured. It does not yet look for a C2PA manifest bound
  to the document — [C2PA 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html)
  (April 2026) added one in §A.7, along with a `c2pa.ai-disclosure` assertion in
  §18.28, and a rule for it is [open](https://github.com/Tippel-AI/markproof/issues/18).
  What markproof will not do is invent a `<meta>` convention of its own and call
  the result conformance.
- **Not a detection check.** Article 50(2) asks for marking *and* detectability,
  and the Commission Guidelines are explicit that satisfying one does not
  discharge the other. markproof measures whether the mark arrived. Whether a
  third party can detect it — the second limb — is not something a probe against
  your endpoint can answer.

## Regulatory context

Article 50 of the EU AI Act has applied since **2 August 2026**. The Digital Omnibus on AI — [Regulation (EU) 2026/1744](http://data.europa.eu/eli/reg/2026/1744/oj) of 8 July 2026, in force since 27 July 2026 — postponed the high-risk obligations for Annex III systems to **2 December 2027** and those for AI inside regulated products to **2 August 2028**. It did not relax the Article 50 transparency duties themselves; the one date it moved there is the transition for systems already on the market before 2 August 2026, which have until **2 December 2026** to retrofit machine-readable marking under Art. 50(2). (Reference checked against EUR-Lex on 31 August 2026. What the dates mean for your system is a question for a lawyer, not for this README.)

Rulepacks are derived from the Commission's Article 50 guidelines (20 July 2026) and the Code of Practice on Transparency. They are versioned, cite the clause they implement, and are published under CC-BY-4.0 so you can reuse them outside this tool.

## Disclaimer

markproof is not affiliated with, endorsed by, or sponsored by Google DeepMind (SynthID), Adobe / the Content Authenticity Initiative (C2PA), or the European Commission. All trademarks are the property of their respective owners.

markproof performs technical conformance testing. It is not legal advice and produces no certification. A passing report is evidence that specific checks passed at a specific time — nothing more.

Where the tool stops is written out in full — every scope limit, stated on purpose — in [`docs/DISCLAIMER.md`](docs/DISCLAIMER.md).

## Licence

Code is Apache-2.0. Rulepacks, patterns, prompt sets, and documentation are CC-BY-4.0 (they derive from CC-BY-licensed Commission material). See [`LICENSE`](LICENSE), [`LICENSE-DATA`](LICENSE-DATA), and [`NOTICE`](NOTICE).

---

Built by [Lukas Friedrich](https://tippel.ai) at Tippel, who builds production AI systems that can prove what they did — which is the same reason this one exists: content marking is only worth anything if it survives to the endpoint a user actually reaches, and nothing checks that today.
