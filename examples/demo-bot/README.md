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

## Status

Empty. This is an M1 deliverable.

- TODO(M1): FastAPI app with an OpenAI-compatible `/v1/chat/completions`,
  disclosure present in `pass` mode and absent in `fail` mode.
- TODO(M2): media endpoint returning a C2PA-signed asset in `pass` mode and an
  unsigned one in `fail` mode.
- TODO(M3): a watermarked variant, so the SynthID end-to-end path has something
  real to detect.
- TODO(M4): `conformance-demo.yml` runs the Action against this app — the green
  badge in the README is the live proof, not a claim.
