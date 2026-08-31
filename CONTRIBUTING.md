<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# Contributing

markproof is maintained by [Tippel](https://tippel.ai). It is pre-release; the
API and the rulepack format can still change.

## Setup

```sh
uv sync --extra dev
uv run ruff check .
uv run mypy
uv run pytest
```

Optional extras when you touch those paths: `--extra synthid` (transformers and
torch), `--extra ui` (Playwright), `--extra pdf`, `--extra pdf-html`. The default
path must keep working without any of them.

## Rule proposals are the most useful contribution

If you have read the Guidelines or the Code of Practice and think a checkable
obligation is missing, open a rule proposal. Include the clause or margin number
and a sketch of how a machine could decide it. Rules that cannot be decided
deterministically are still welcome — they become WARN rules with evidence,
which is honest, rather than PASS rules that guess.

## Ground rules

- **No LLM in the evaluation path.** No LLM judge, no heuristic score deciding
  PASS or FAIL. Undecidable means WARN plus evidence.
- **Determinism is a feature, not a nicety.** `evaluate(rulepack, evidence)` is a
  pure function; identical inputs must produce byte-identical findings. If your
  change introduces ordering, time or locale dependence, it will fail the
  determinism job.
- **Every file carries an SPDX header.** `Apache-2.0` for code,
  `CC-BY-4.0` for anything under `src/markproof/rulepacks/`,
  `src/markproof/patterns/` and `docs/`.
- **No verbatim normative text in rulepacks.** Paraphrase and cite the clause
  number; keep the mandatory `attribution:` line. One short quote is the ceiling.
- **Test media must be your own work.** No third-party copyrighted media enters
  `tests/fixtures/media/`, not even a harmless-looking example image. Record the
  provenance of every fixture in that directory's README.
- **No third-party branding.** No logos, and no component named after someone
  else's trademark.
- **Don't benchmark named commercial providers.** Examples and demos use our own
  demo-bot or anonymised endpoints.

## Pull requests

Small and focused. Add or update golden files in the same PR as the behaviour
change, and say in the description why the new golden output is correct — an
unreviewed golden update quietly redefines what "conformant" means.

By contributing you agree that your contributions are licensed under Apache-2.0
(code) or CC-BY-4.0 (rulepacks, patterns, docs), matching the file you touch.

## Security

Do not open a public issue for vulnerabilities. See [SECURITY.md](SECURITY.md).
