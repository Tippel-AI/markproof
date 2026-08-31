<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: Apache-2.0
-->

# markproof GitHub Action

Runs `markproof run` against a live endpoint, writes the Markdown summary into
the job summary, uploads the signed report as a workflow artifact, and fails the
step when a rule fails. A thin composite wrapper — nothing it does is
unreachable from the command line.

Composite rather than Docker on purpose: a Docker action pays an image pull on
every run, and this check should add seconds to a pipeline, not minutes.

## Quick start

```yaml
name: article-50

on:
  pull_request:
  # Article 50 is about the endpoint that is deployed, not the code that was
  # merged. A nightly run against production catches the model swap nobody
  # opened a PR for.
  schedule:
    - cron: "17 6 * * *"

permissions:
  contents: read

jobs:
  markproof:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: Tippel-AI/markproof/action@v0.1.0
        with:
          config: markproof.yaml
        env:
          # Whatever your probes reference via `auth: { env: ... }`
          MARKPROOF_TOKEN: ${{ secrets.STAGING_API_TOKEN }}
          MARKPROOF_SIGNING_KEY: ${{ secrets.MARKPROOF_SIGNING_KEY }}
```

That is the whole integration. The report lands in the run's artifacts, the
summary in the job summary, and a FAIL turns the step red.

## Inputs

| Input             | Default            | What it does                                                                                                                        |
| ----------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `config`          | `markproof.yaml`   | Path to the target config, relative to the workspace.                                                                                 |
| `rulepack`        | *(config)*         | Rulepack id (`art50-eu-2026.07`) or path. Overrides the one named in the config.                                                      |
| `report-dir`      | `markproof-report` | Directory that receives `report.json` and `summary.md`.                                                                               |
| `fail-on`         | `fail`             | `fail` goes red on a FAIL finding; `warn` also goes red on WARN. SKIP never fails.                                                    |
| `python-version`  | `3.12`             | Python for markproof's own environment. Empty string skips `actions/setup-python` and uses the interpreter on PATH.                   |
| `extras`          | *(none)*           | Comma-separated optional extras, e.g. `synthid` for text-watermark verification, `pdf` for the pure-Python PDF renderer.              |
| `version`         | `0.1.0`            | PyPI version to install. Ignored when the action runs from a checkout of this repository, which installs that source instead.         |
| `upload-artifact` | `true`             | Upload `report-dir` with `actions/upload-artifact`.                                                                                   |
| `artifact-name`   | `markproof-report` | Artifact name. Must be unique within the workflow run — give matrix jobs distinct names.                                               |

## Outputs

| Output         | What it is                                                                                                                  |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `report-path`  | Path to `report.json`.                                                                                                       |
| `summary-path` | Path to `summary.md`.                                                                                                        |
| `exit-code`    | `markproof run`'s own exit code: `0` clean, `1` at least one FAIL, `2` configuration or probe error. Set even when red.       |

Reading an output after a red step needs `if: always()` on the reading step,
and `continue-on-error: true` on the markproof step if the job should carry on:

```yaml
      - uses: Tippel-AI/markproof/action@v0.1.0
        id: markproof
        continue-on-error: true

      - if: always()
        run: echo "markproof exited ${{ steps.markproof.outputs.exit-code }}"
```

## Signing the report

The signing key is an Ed25519 private key in PEM form. It belongs in a
repository or organisation secret and **never in the repository**, not in
`markproof.yaml`, not in a committed `.pem`, not base64-wrapped in a file
someone assumes nobody will look at. Anyone holding it can sign a report that
claims your endpoint was conformant.

Generate it once, locally:

```bash
markproof keygen --out-dir ./keys      # keys/private.pem, keys/public.pem
```

Paste the contents of `keys/private.pem` into a secret named
`MARKPROOF_SIGNING_KEY`, delete the local copy, and commit `keys/public.pem` —
the public half is meant to be published, so auditors can verify a report
without asking you for anything.

The action passes the environment straight through, so the variable is set on
the step (or the job), never as an input — inputs are more easily echoed into a
log than environment variables are:

```yaml
        env:
          MARKPROOF_SIGNING_KEY: ${{ secrets.MARKPROOF_SIGNING_KEY }}
```

Verifying, anywhere, later:

```bash
markproof verify-report markproof-report/report.json --key keys/public.pem
```

The action exports `MARKPROOF_BIN` into the job environment, so a follow-up step
can verify without installing anything:

```yaml
      - if: always()
        run: >-
          "$MARKPROOF_BIN" verify-report
          "${{ steps.markproof.outputs.report-path }}" --key keys/public.pem
```

## uv or pip

The action uses `uv` when the runner already has it on PATH and `pip` otherwise,
and says which one it chose in the log.

It does not install uv on your behalf. uv is the faster tool by a wide margin —
resolving and installing markproof's dependency set is seconds rather than tens
of seconds, and the gap widens sharply with the `synthid` extra, which drags in
torch. But installing a package manager into somebody else's runner to make our
own step faster is not a decision this action gets to make for you. If you want
the speedup, ask for it:

```yaml
      - uses: astral-sh/setup-uv@v10.0.1   # no v10 major tag exists; pin exactly
        with:
          enable-cache: true
      - uses: Tippel-AI/markproof/action@v0.1.0
```

Set `MARKPROOF_INSTALLER` to `uv` or `pip` to force either one; `auto` (the
default) is the detection above.

Either way markproof is installed into its own virtualenv under `RUNNER_TEMP`,
never into the interpreter your workflow uses. A conformance checker that
injects httpx, pydantic and possibly torch into the environment it is checking
can mask the very dependency problem the pipeline exists to catch.

## Verifying text marking

`synthid-detect` rules need the optional extra, which pulls `transformers` and
`torch` and downloads the tokenizer your watermark config names:

```yaml
        with:
          extras: synthid
```

On the uv path the action defaults `UV_TORCH_BACKEND=cpu` unless you set it,
because the default PyPI torch wheel for Linux is the CUDA build — gigabytes, on
a runner with no GPU. On the pip path, name the CPU index yourself:

```yaml
    env:
      PIP_EXTRA_INDEX_URL: https://download.pytorch.org/whl/cpu
```

Cache the tokenizer with `actions/cache` on `HF_HOME` if you would rather not
depend on the model hub being up.

Without the extra, keep `text_marking` out of your config: disclosure and media
rules run on the default install with no system packages at all, which is the
whole point of the default output path.

## Failing on warnings

`fail-on: warn` reads the WARN count from `report.json` and fails the step when
it is non-zero. Worth knowing before you turn it on: markproof reports WARN when
it saw something it cannot confidently judge — a near-miss disclosure, an
unreadable download. Those are for a human to look at. A pipeline that goes red
on ambiguity trains people to ignore it, which is why `fail` is the default.

An exit code of `2` fails the step regardless of `fail-on`: it means a
configuration or probe error, so nothing was actually checked, and a green build
would be a lie.

## What happens on red

The summary and the artifact upload run even when the check fails. A failed
check whose evidence is lost is worthless — the FAIL is exactly the moment
somebody needs to read the report. Only a cancelled job skips them.

## Runner requirements

Nothing beyond Python and network access to your endpoint. No `apt install`, no
system libraries — the default output path is JSON plus Markdown, and PDF stays
an opt-in extra so it can never break a minimal container image.

Pinned action versions, verified on 2026-08-31: `actions/setup-python@v7`
(v7.0.0) and `actions/upload-artifact@v7` (v7.0.1). If your organisation
requires SHA-pinned third-party actions, vendor this action and rewrite those
two `uses:` lines — the action itself will then install from PyPI, and `version`
selects the release.

## Dogfooding

[`.github/workflows/dogfood.yml`](../.github/workflows/dogfood.yml) runs this
action from the checkout against
[`examples/demo-bot`](../examples/demo-bot) on every push and pull request, in
two modes whose verdict is known in advance — `pass` must exit 0 and `nomark`
must exit 1 — and asserts that the report and summary survive the red run.
