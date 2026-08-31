<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# demo-bot answer texts — provenance record

**Hard rule (Auflage H2): every word in this directory is our own production.**
Nothing here was sampled from a language model, copied from another assistant or
lifted from any corpus. Every phrase is written out in [`lattice.py`](lattice.py);
[`make_texts.py`](make_texts.py) only decides *which* of them to use.

The demo-bot serves these files as-is; it never marks at request time. Marking is
a search over wordings, so a bot that marked per request would make its own
output depend on the tokenizer build and the torch version installed that day —
see [Determinism](../README.md#determinism).

## What is in here

Sixteen texts: eight answer variants in two renderings.

A variant is `<lang>-<kind>-<turn>`. `kind` is whether the user asked outright
what they are talking to; `turn` is whether this is the opening answer. Together
they reproduce the four branches of `build_answer` in `app.py`.

| Rendering | Chosen by | Served in |
|---|---|---|
| `marked/` | a beam search that maximises the g-value statistic | `DEMO_MODE=pass`, `DEMO_MODE=wrongtype` |
| `plain/`  | a fixed stride through each pool that never reads a g-value | `DEMO_MODE=nomark` |

**Both renderings come from the same lattice.** Same length, same register, same
disclosure sentences, same enumerations — only the word choice at each slot
differs. That is the whole design: a detector that separates `pass` from
`nomark` is reading the marking, not the prose. It is the text-side counterpart
of `media/`, where three fixtures share pixel-for-pixel identical image data and
differ only in provenance.

## Measured

Config: [`../watermark_config.json`](../watermark_config.json) — `gpt2`,
`ngram_len=5`, three keys. Regenerate with `make_texts.py`, which prints this
table and refuses to write a file that misses any threshold.

| File | Tokens | mean-g | context-masked | n-grams kept |
|---|---:|---:|---:|---:|
| `marked/de-generic-first.txt`  | 493 | 0.7635 | 0.7642 | 482/489 |
| `marked/de-generic-later.txt`  | 479 | 0.7726 | 0.7726 | 475/475 |
| `marked/de-identity-first.txt` | 521 | 0.7498 | 0.7503 | 510/517 |
| `marked/de-identity-later.txt` | 505 | 0.7611 | 0.7618 | 494/501 |
| `marked/en-generic-first.txt`  | 322 | 0.8543 | 0.8543 | 318/318 |
| `marked/en-generic-later.txt`  | 312 | 0.8669 | 0.8669 | 308/308 |
| `marked/en-identity-first.txt` | 339 | 0.8299 | 0.8299 | 335/335 |
| `marked/en-identity-later.txt` | 331 | 0.8430 | 0.8452 | 323/327 |
| `plain/de-generic-first.txt`   | 498 | 0.4919 | 0.4922 | 491/494 |
| `plain/de-generic-later.txt`   | 482 | 0.4937 | 0.4940 | 475/478 |
| `plain/de-identity-first.txt`  | 526 | 0.4923 | 0.4926 | 519/522 |
| `plain/de-identity-later.txt`  | 510 | 0.4954 | 0.4957 | 503/506 |
| `plain/en-generic-first.txt`   | 309 | 0.5268 | 0.5268 | 305/305 |
| `plain/en-generic-later.txt`   | 300 | 0.5304 | 0.5304 | 296/296 |
| `plain/en-identity-first.txt`  | 326 | 0.5186 | 0.5186 | 322/322 |
| `plain/en-identity-later.txt`  | 317 | 0.5218 | 0.5218 | 313/313 |

Marked lands in **0.7498 – 0.8669**, plain in **0.4919 – 0.5304**, against an
`expected_mean_g_value` of 0.74999 for this vocabulary. The shortest text is 300
tokens, well past the 100 `MPF-T-001` asks for and past the 250 the milestone
issue asks for.

Two columns rather than one because the reference detector drops n-grams whose
`ngram_len - 1` context it has already seen: a marker that has committed to a
context does not get a second vote from it. The two numbers barely differ here —
at most 98 % of n-grams survive the mask — because the lattice draws its
enumerations *without replacement* and its prose from pools of twenty-plus. A
check adopting either convention can be read against these fixtures.

### Against the shipped thresholds

`MPF-T-001` in `art50-eu-2026.07` reads `watermarked_at: 0.70` and
`not_watermarked_below: 0.56`. The worst case on each side is
`marked/de-identity-first` at 0.7498 (0.05 above the bar) and
`plain/en-generic-later` at 0.5304 (0.03 below it). `make_texts.py` asserts both
bounds on every run, with its plain ceiling set to that rule's threshold
exactly, so a regeneration cannot quietly produce a control sample the rule
would call watermarked.

The floor it asserts is stricter than the rule's — 0.74, at
`expected_mean_g_value` rather than at 0.70. A fixture that only just cleared
the threshold would let the threshold drift upward without anything noticing.

## Why German scores lower than English

The same lattice design, the same config, a 0.09 gap. GPT-2's BPE spends about
3.4 tokens on a German word and 1.2 on an English one, and a slot's leverage on
the statistic falls off as `1/sqrt(tokens it covers)`. German choices are simply
more expensive. This is a property of the tokenizer, not of the marking, and it
is worth knowing before reading any single number as "the" watermark strength.

## Why the config carries only three keys

Depth is the one parameter this demo cannot pick freely.

A real generator marks by tournament sampling over its model's own candidate
continuations, and reaches `expected_mean_g_value` ≈ 0.75 at *any* depth,
because every layer gets its own two-way contest. A search over a hand-written
lattice cannot: it has to find one phrasing that scores well on all layers at
once, and what it can achieve falls off as `1/sqrt(depth × tokens per choice)`.
Measured on this lattice, German reaches 0.76 at three keys, 0.72 at four and
0.64 at nine. Three is the largest depth at which both languages still sit in
the band real watermarked text occupies.

That costs headroom in the search, not detection strength. Three layers over
roughly 480 n-grams is about 1 400 Bernoulli draws and a null standard deviation
near 0.013, which puts twenty standard deviations between the marked and plain
fixtures. **A real deployment, marking with a model rather than a word list,
should use many more keys.** Do not read three as a recommendation.

## Regenerating

Needs the dev environment, not the demo-bot's own `requirements.txt`:

```bash
pip install "transformers>=5" "torch>=2"
python examples/demo-bot/text/make_texts.py
```

CPU only; nothing here loads a model, and the tokenizer is the sole download.
The run is deterministic — no RNG, ties broken on text order — so the same
inputs give byte-identical files and the table above stays valid. Update it if
you change the lattice, the config or the tokenizer, and expect `MANIFEST.json`
to move with it.

`make_texts.py` refuses to write a set that would leave the demo broken. It
checks that the finished string tokenises to exactly what the search scored
(a BPE merge across a slot boundary would mean the detector sees a different
sequence than the search optimised), that every required disclosure sentence
survived, that each text clears 250 tokens, and that marked and plain land on
the correct sides of their thresholds.

`app.py` re-checks the disclosure sentences when it boots, so a regeneration
that dropped one stops the bot at startup instead of silently serving a target
that answers but no longer discloses.
