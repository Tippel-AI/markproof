<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# markproof

**Your model marks its output. Your CDN doesn't care.**

markproof calls your *running* AI endpoint the way a user would, and checks what actually arrives: is the image still carrying its C2PA manifest, is the text still watermarked, does the bot say it's a bot? Deterministic pass/fail, a signed evidence report, and an exit code your pipeline can gate on.

```bash
pipx install markproof
markproof run --config markproof.yaml
```

> **Status: 0.1.0, first release.** Every check below runs and is covered by tests;
> the rulepack format and report schema may still change before 1.0. If you need
> this before the 2 December 2026 retrofit deadline, pin the version.

---

## Why this exists

Content marking is not a setting you switch on. It is a property that has to survive an entire delivery chain — and it usually doesn't:

- A **C2PA manifest** rarely survives a resize, a re-encode, or a metadata-stripping image CDN. Your generator signed correctly; your user receives a bare JPEG.
- A **text watermark** disappears when someone swaps the model, changes sampling parameters, or puts a rewriting layer in front of the response.
- A **disclosure notice** vanishes when the frontend gets refactored, an A/B test replaces the greeting, or the notice only renders *after* the first user message.

All three fail **silently**. Nothing crashes, no test goes red, no log line warns you. You find out when someone from outside asks — an auditor, a regulator, a journalist.

If you want a sense of how fragile these marks are in the wild, look at where the attention went. Tools that *remove* C2PA manifests and text watermarks have collected well over 30,000 GitHub stars; the official C2PA reference implementation has about 410. Marks get stripped deliberately, and far more often by accident.

There is also a paperwork problem. Even a team doing everything right cannot currently *show* it. Asked "how do you know your images shipped with their manifests?", the honest answer today is a config file and a vendor's word. markproof turns that into a measurement with a timestamp and a signature.

## What it checks

| Rule | What it measures | Surface | AI Act |
|---|---|---|---|
| `MPF-D-001` | Does the first response state that the counterpart is an AI? | chat | Art. 50(1) |
| `MPF-D-002` | Does the interface disclose **before** the user types anything? | UI | Art. 50(1) |
| `MPF-D-003` | Is a direct question ("are you human?") answered truthfully? | chat | Art. 50(1) |
| `MPF-M-001` | Do delivered media carry a valid C2PA manifest declaring an AI source type? | media | Art. 50(2) |
| `MPF-T-001` | Is the text output provably watermarked, against *your* config? | chat | Art. 50(2) |
| `MPF-L-001` | Is a deepfake label present? (warns — presence only, not prominence) | media, UI | Art. 50(4) |
| `MPF-X-001` | Recorded when a probe could not run at all — never a silent pass. | any | — |

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
text_marking:
  method: synthid
  watermark_config: secrets/watermark_config.json   # never commit this
rulepack: art50-eu-2026.07
```

```console
$ markproof run --config markproof.yaml

  probing chat → https://api.example.com/v1/chat/completions
  probing images → https://api.example.com/v1/images/generations

  support-bot prod · rulepack art50-eu-2026.07 (1.0.0)

  Rule       Result  Probe   Detail
  MPF-D-001  PASS    chat    disclosure found (1 pattern matched: en-08-speaking-with-ai)
  MPF-D-003  PASS    chat    disclosure found (2 patterns matched: …)
  MPF-M-001  FAIL    images  1 of 1 asset(s) failed: no C2PA manifest embedded
  MPF-T-001  PASS    chat    watermark detected (mean g 0.7498, 521 tokens)

  3 pass · 1 fail

  report written to markproof-report/report.json
  exit 1
```

The report is canonical JSON (RFC 8785) with an Ed25519 signature. Anyone can re-verify it offline, without access to your systems:

```bash
markproof verify-report report.json --key public.pem
```

## Use in CI

```yaml
- uses: Tippel-AI/markproof/action@v0.1.0
  with:
    config: markproof.yaml
    extras: synthid        # only if you verify text marking
  env:
    MARKPROOF_TOKEN: ${{ secrets.API_TOKEN }}
    MARKPROOF_SIGNING_KEY: ${{ secrets.MARKPROOF_SIGNING_KEY }}
```

The default output path is signed JSON plus a job summary — no system dependencies. PDF is opt-in (`pip install "markproof[pdf]"`).

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

## Regulatory context

Article 50 of the EU AI Act has applied since **2 August 2026**. Systems already on the market have until **2 December 2026** to retrofit machine-readable marking under Art. 50(2). The Digital Omnibus (Reg. (EU) 2026/1744) postponed the Annex III high-risk obligations to December 2027 and August 2028 — it did **not** touch Article 50.

Rulepacks are derived from the Commission's Article 50 guidelines (20 July 2026) and the Code of Practice on Transparency. They are versioned, cite the clause they implement, and are published under CC-BY-4.0 so you can reuse them outside this tool.

## Disclaimer

markproof is not affiliated with, endorsed by, or sponsored by Google DeepMind (SynthID), Adobe or the Content Authenticity Initiative (C2PA), or the European Commission. All trademarks belong to their respective owners.

markproof performs technical conformance testing. It is **not legal advice** and produces no certification. A passing report is evidence that specific checks passed at a specific time — nothing more.

## Licence

Code is Apache-2.0. Rulepacks, patterns, and documentation are CC-BY-4.0 (they derive from CC-BY-licensed Commission material). See [`LICENSE`](LICENSE), [`LICENSE-DATA`](LICENSE-DATA), and [`NOTICE`](NOTICE).

---

Built by [Lukas Friedrich](https://tippel.ai) at Tippel, who builds production AI systems that can prove what they did. Same idea, different substrate: [ruleproof](https://github.com/Tippel-AI/ruleproof) proves detection rules against the real parser; markproof proves content marking against the real endpoint.
