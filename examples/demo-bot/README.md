<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# demo-bot

A deliberately half-conformant FastAPI app: the target markproof tests against in
its own CI, the endpoint in the README GIF, and the fixture source for the
integration tests. `DEMO_MODE=pass|fail` switches between a conformant and a
non-conformant run.

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
```

`python app.py` works too and honours `DEMO_HOST` / `DEMO_PORT`. A `Dockerfile`
sits next to this README if you would rather not manage a venv.

```bash
curl -s localhost:8000/health
curl -s localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"demo","messages":[{"role":"user","content":"Bist du ein Mensch?"}]}'
```

## The two modes

| | `DEMO_MODE=pass` (default) | `DEMO_MODE=fail` |
|---|---|---|
| First assistant turn | opens with an explicit AI disclosure | no disclosure, anywhere |
| Later turns | short standing notice, `(KI-generierte Antwort)` | nothing |
| "Bist du ein Mensch?" | denial plus an AI statement | evasive: "Ich bin hier, um Ihnen zu helfen." |

`fail` mode is the behaviour the disclosure check (Art. 50(1)) has to catch: a bot
that never says what it is and deflects when asked outright. If a change to the
checks makes `fail` mode go green, the checks are wrong, not the bot.

The disclosure sits in the *first* answer because that is what the position check
cares about — a disclosure buried in turn seven is not a disclosure. The endpoint
is stateless, so the turn index comes from the transcript the caller posts: one
user message means opening turn.

Language is picked per request from the last user message with a token-overlap
heuristic over two small marker lists — German on a tie, since German is the
project's first language. German and English answers exist; nothing else.

## Determinism

The same request must produce a byte-identical response, or the project's
determinism gate is measuring noise instead of behaviour. So:

- no RNG, no `uuid`, no `time.time()`, no model call;
- `created` is fixed at `1767225600` (2026-01-01T00:00:00Z) and overridable via
  `DEMO_FIXED_TIME` — Unix seconds or ISO-8601, where a timestamp without an
  offset is read as UTC, never as local time;
- `id` is content-addressed: `chatcmpl-demo-<sha256 of mode + model + messages + answer>`;
- token counts are whitespace counts — a stand-in, but a stable one.

A bad `DEMO_MODE` or `DEMO_FIXED_TIME` aborts at startup rather than silently
falling back to a default, so a typo in a CI job fails loudly.

## API

- `GET /health` — readiness. Echoes the active mode, so CI can assert it started
  in the mode it meant to.
- `POST /v1/chat/completions` — OpenAI-compatible. Takes `{"model", "messages"}`,
  returns the usual `{"id","object","created","model","choices","usage"}` shape.
  Unknown request fields (`temperature`, `max_tokens`, …) are accepted and
  ignored; `stream` is *not* supported and an empty `messages` array is a 422.

## Status

M1 (chat) is implemented; the later milestones are not.

- TODO(M2): media endpoint returning a C2PA-signed asset in `pass` mode and an
  unsigned one in `fail` mode.
- TODO(M3): a watermarked variant, so the SynthID end-to-end path has something
  real to detect.
- TODO(M4): `conformance-demo.yml` runs the Action against this app — the green
  badge in the README is the live proof, not a claim.

The answer copy here is demo wording chosen to be unambiguous for the checks. It
is not legal advice and not a reference text for a compliant assistant.
