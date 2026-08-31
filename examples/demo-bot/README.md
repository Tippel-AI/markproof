<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# demo-bot

A deliberately half-conformant FastAPI app: the target markproof tests against in
its own CI, the endpoint in the README GIF, and the fixture source for the
integration tests. It answers chat and it generates images, both under
`DEMO_MODE=pass|fail`, which switches between a conformant and a non-conformant
run. Two narrower modes isolate one obligation each: `wrongtype` for media
marking, `nomark` for text marking.

Testing against our own demo endpoint is also what keeps the marketing clean
(Auflage H3): no blog post, GIF or social asset ever shows a named third-party
provider failing a check.

It is not a model server and there is no model behind it. Every answer is a pure
function of the request, which is the whole point — see [Determinism](#determinism).

## Run it

Needs Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# conformant target (default)
uvicorn app:app --host 127.0.0.1 --port 8000

# non-conformant target
DEMO_MODE=fail uvicorn app:app --host 127.0.0.1 --port 8000

# conformant everywhere except the text watermark
DEMO_MODE=nomark uvicorn app:app --host 127.0.0.1 --port 8000
```

`python app.py` works too and honours `DEMO_HOST` / `DEMO_PORT`. A `Dockerfile`
sits next to this README if you would rather not manage a venv.

```bash
curl -s localhost:8000/health
curl -s localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"demo","messages":[{"role":"user","content":"Bist du ein Mensch?"}]}'
curl -s localhost:8000/v1/images/generations \
  -H 'Content-Type: application/json' \
  -d '{"model":"demo","prompt":"Ein einfaches Testbild."}'
```

## The modes

| | `DEMO_MODE=pass` (default) | `DEMO_MODE=fail` |
|---|---|---|
| First assistant turn | opens with an explicit AI disclosure | no disclosure, anywhere |
| Later turns | short standing notice, `(KI-generierte Antwort)` | nothing |
| "Bist du ein Mensch?" | denial plus an AI statement | evasive: "Ich bin hier, um Ihnen zu helfen." |
| Answer text | watermarked, mean-g 0.75–0.87 | unmarked, and far too short to score |
| Generated image | valid C2PA manifest, `digitalSourceType = trainedAlgorithmicMedia` | no manifest at all |

`fail` mode is the behaviour the disclosure check (Art. 50(1)) has to catch: a bot
that never says what it is and deflects when asked outright. If a change to the
checks makes `fail` mode go green, the checks are wrong, not the bot.

The image half of `fail` is the same idea one obligation over: not an exotic
failure, but the ordinary one. Somebody wired up a generator that marks its
output correctly, and then a CDN, a thumbnailer or a "strip metadata for privacy"
step downstream dropped the chunk. Nobody notices, because the picture still
looks exactly the same — the two files differ in provenance and in nothing else.

### A third mode, for media only

`DEMO_MODE=wrongtype` behaves like `pass` on the chat endpoint and serves an
image whose manifest is present, embedded and cryptographically valid, but whose
action claims `algorithmicMedia` — algorithmically produced, yet not by a trained
model.

It exists because it is the case only an assertion-level check catches. Every
"does this asset have Content Credentials?" tool says yes. The signature
verifies, the hash bindings hold, and the asset still does not do what
Art. 50(2) asks of AI-generated media. A substring match for `algorithmicmedia`
waves it through too, which is worth a test of its own.

The chat side stays conformant on purpose: the defect lives in one manifest
field, and a mode that also broke the chat would stop isolating it. Answers are
byte-identical to `pass`, with one exception — the completion `id` is content
addressed over the mode as well, so the same answer carries a different `id`.

### A fourth mode, for text marking

`DEMO_MODE=nomark` is the control the text-marking check is measured against. It
discloses exactly as `pass` does and serves the same correctly signed image; the
only difference is that its answer text **carries no watermark**.

It exists so that a marking finding cannot be mistaken for a disclosure finding.
The two modes draw their answers from the same lattice of interchangeable
phrasings, so a `pass` answer and a `nomark` answer to the same prompt have the
same length, the same register, the same enumerations and the same disclosure
sentences, and differ only in which synonym was taken at each slot. A detector
that separates them is reading the token sequence and nothing else. Measured:

```
                        pass      nomark
Hallo, können Sie …    0.7635    0.4919     (493 / 498 tokens)
Bist du ein Mensch?    0.7498    0.4923     (521 / 526 tokens)
Hello, can you help?   0.8543    0.5268     (322 / 309 tokens)
```

That is the same idea as `wrongtype`, one obligation over: hold everything
constant except the one property under test. Where `wrongtype` isolates a single
manifest field, `nomark` isolates the token sequence.

Note what `fail` does *not* do here. Its answers stay short and undisclosed, so
it remains purely the Art. 50(1) fixture; it is not a second unmarked sample.
The controlled pair for marking is `pass` against `nomark`.

The disclosure sits in the *first* answer because that is what the position check
cares about — a disclosure buried in turn seven is not a disclosure. The endpoint
is stateless, so the turn index comes from the transcript the caller posts: one
user message means opening turn.

Language is picked per request from the last user message with a token-overlap
heuristic over two small marker lists — German on a tie, since German is the
project's first language. German and English answers exist; nothing else.

## Text marking

In `pass` and `wrongtype` the answers are watermarked: their **token sequence**
carries a SynthID-style mark. That is what makes this endpoint a live target for
the Art. 50(2) text check rather than a mock of one.

The answers are long — 300 to 526 tokens — because a text watermark is a
statistical property and a one-line reply carries no signal worth a verdict.
`MPF-T-001` asks for 100 tokens; the shipped texts clear that several times over.

Nothing is marked at request time. The texts are composed once, offline, by
[`text/make_texts.py`](text/make_texts.py) and served from `text/`, for the same
reason images are signed offline, and one more: marking is a *search over
wordings*, so a bot that searched per request would tie its own output to the
tokenizer and torch build installed that day. Committed files make the
determinism guarantee unconditional.

There is no model here and none is needed. A SynthID-style watermark is a
property of the token sequence, not of whatever produced it, so a tokenizer and
`compute_g_values` are enough to build and to check one. See
[`text/README.md`](text/README.md) for the measured numbers per file, why German
scores about 0.09 lower than English under the same config, and why the demo
config carries only three keys.

### `watermark_config.demo.json`

Detection needs the *generation-side* configuration, which is exactly why
markproof is a self-conformance test: it verifies an operator against their own
declared marking, rather than trying to detect AI text in general. So the
operator hands markproof the config they generate with:

```json
{
  "tokenizer": "gpt2",
  "ngram_len": 5,
  "keys": [50841, 12703, 39218],
  "sampling_table_size": 65536,
  "sampling_table_seed": 0,
  "context_history_size": 1024
}
```

**In this demo that file is not a secret — in production it is.** The `keys` are
the watermark. Anyone holding them can test whether a given text carries your
mark, and, more to the point, can strip or forge it. Ours are committed because
a demo target nobody can check is not a demo target; a real deployment keeps
them in a secrets manager or CI secret and hands markproof a path, never a
committed file. The repository's `.gitignore` already treats
`watermark_config*.json` as a secret class for exactly this reason — the demo's
copy is a deliberate exception to that rule, not an oversight.

**Why the file is called `watermark_config.demo.json`.** `WatermarkConfig`
rejects unknown fields, so the file cannot carry a `"_comment"` saying what it
is; a JSON object of six numeric-looking settings looks the same whether the
keys are throwaway or production. The name is therefore the marking, and it is
the only one that survives someone copying the file out of this repository as a
template. If you start from it, replace the `keys` before you mark anything and
rename it back to `watermark_config.json`, which is the name `.gitignore`
protects.

`gpt2` is the tokenizer because it is the most widely available one there is:
pure byte-level BPE in a single `tokenizer.json`, no `sentencepiece`, no gated
download, very likely already in the cache of any machine that has run
`transformers`. It is not what a German assistant would really use, and
[`text/README.md`](text/README.md) explains what that costs.

## Determinism

The same request must produce a byte-identical response, or the project's
determinism gate is measuring noise instead of behaviour. So:

- no RNG, no `uuid`, no `time.time()`, no model call;
- `created` is fixed at `1767225600` (2026-01-01T00:00:00Z) and overridable via
  `DEMO_FIXED_TIME` — Unix seconds or ISO-8601, where a timestamp without an
  offset is read as UTC, never as local time;
- `id` is content-addressed: `chatcmpl-demo-<sha256 of mode + model + messages + answer>`;
- token counts are whitespace counts — a stand-in, but a stable one;
- images are read from `media/`, never signed at request time. Signing is not a
  pure function: every signature carries a fresh ECDSA nonce and a fresh signing
  time, so a bot that signed per request would answer the same question with
  different bytes each time;
- answer texts are read from `text/`, never marked at request time — marking is
  a search, and its result depends on the tokenizer and torch build doing the
  searching.

A bad `DEMO_MODE`, `DEMO_FIXED_TIME` or `DEMO_PUBLIC_BASE_URL` aborts at startup
rather than silently falling back to a default, so a typo in a CI job fails
loudly. A missing image fixture does the same, and so does a missing answer text
— or one that no longer contains the disclosure sentence it is supposed to
carry. A bot that still answers but has quietly stopped disclosing is the one
failure a conformance target must never have.

## API

- `GET /health` — readiness. Echoes the active mode, so CI can assert it started
  in the mode it meant to.
- `POST /v1/chat/completions` — OpenAI-compatible. Takes `{"model", "messages"}`,
  returns the usual `{"id","object","created","model","choices","usage"}` shape.
  Unknown request fields (`temperature`, `max_tokens`, …) are accepted and
  ignored; `stream` is *not* supported and an empty `messages` array is a 422.
- `POST /v1/images/generations` — OpenAI-compatible. Takes
  `{"model", "prompt", "n", "size", "response_format"}` and returns
  `{"created", "data": [...]}`.
- `GET /media/{name}` — the stored assets, `Content-Type: image/png`, bytes
  untouched.

### `POST /v1/images/generations`

```bash
curl -s localhost:8000/v1/images/generations \
  -H 'Content-Type: application/json' \
  -d '{"model":"demo","prompt":"Ein Leuchtturm im Nebel","n":1,"response_format":"url"}'
# {"created":1767225600,"data":[{"url":"http://localhost:8000/media/demo-signed.png"}]}

curl -s localhost:8000/v1/images/generations \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Ein Leuchtturm im Nebel","response_format":"b64_json"}'
# {"created":1767225600,"data":[{"b64_json":"iVBORw0KGgo…"}]}
```

`response_format` defaults to `"url"` and also accepts `"b64_json"`, which
returns the identical bytes inline. Both exist because markproof has to handle
both, and because the two paths fail differently in the wild: a URL is served
through a CDN that may re-encode on the way out, while base64 comes straight
from the generator.

The rest of the fields:

- `prompt` is required and non-empty, then read and discarded. There is no model
  here; the mode, not the prompt, decides what provenance comes back.
- `n` (1–10) repeats the one asset that mode serves. Returning `n` *different*
  images would mean generating them.
- `size` is accepted and ignored. The fixtures are pre-rendered at 512×512, and
  honouring another size would mean rendering and signing per request.
- Anything else in the body is ignored, as on the chat endpoint. An unknown
  `response_format` or an empty `prompt` is a 422.

URLs are absolute and built from the origin the request arrived on, which is what
a probe behind a port mapping needs. Set `DEMO_PUBLIC_BASE_URL` when the address
the outside world uses is not the bound one — a container, a tunnel, a reverse
proxy — or when a test wants a response that does not move with the `Host`
header:

```bash
DEMO_PUBLIC_BASE_URL=https://demo.example uvicorn app:app --port 8000
# {"created":1767225600,"data":[{"url":"https://demo.example/media/demo-signed.png"}]}
```

`GET /media/{name}` serves all three assets by name, in every mode; only the
generation endpoint switches with `DEMO_MODE`. Names are looked up in a table
read at startup and never joined onto a filesystem path, so no request reaches
outside `media/`, and bytes go out exactly as stored — re-encoding an image would
break its C2PA hash bindings and turn a valid manifest into a tampering finding.

The assets themselves, how they were generated, and why the signer is
deliberately untrusted: [`media/README.md`](media/README.md). That file also
carries the one thing a C2PA check has to know before it runs against this
target — the signed fixtures validate as `Valid` while reporting
`signingCredential.untrusted`, so a check that fails on any failure code fails
`pass` mode too.

## Status

M1 (chat), the M2 media endpoint and the M3 marked-text variants are
implemented.

- TODO(M4): `conformance-demo.yml` runs the Action against this app — the green
  badge in the README is the live proof, not a claim.

The answer copy here is demo wording chosen to be unambiguous for the checks. It
is not legal advice and not a reference text for a compliant assistant.
