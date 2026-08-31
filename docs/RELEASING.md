<!--
SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
SPDX-License-Identifier: CC-BY-4.0
-->

# Releasing markproof

`.github/workflows/release.yml` does everything a machine can do: it refuses a tag
that disagrees with the packaged version, runs lint, types and the test matrix,
builds, installs the built wheel into a clean environment and uses it, publishes to
PyPI over Trusted Publishing, and opens a GitHub release from the changelog.

What it cannot do is prove to PyPI who you are. That trust is registered once, by
hand, on pypi.org — section 1. After that a release is section 2, and section 3 is
what to do when it goes sideways.

---

## 1. One-time setup

### 1.1 The GitHub environment

Settings → Environments → **New environment**, named exactly `pypi`.

GitHub would create it implicitly on the first run, but create it yourself so you
can attach the rules that make it worth having:

- **Required reviewers** — add yourself. Every upload then waits for one click. For
  the first few releases this is the cheapest safety net you will ever install.
- **Deployment branches and tags** — restrict to tags matching `v*`, so nothing
  else can ever reach the environment that holds the publishing identity.

### 1.2 The pending publisher on PyPI

`markproof` does not exist on PyPI yet, so this is a *pending* publisher and lives
on your account rather than on a project.

1. Sign in on [pypi.org](https://pypi.org) with 2FA enabled.
2. Go to **Your account → Publishing**: <https://pypi.org/manage/account/publishing/>
3. Under **GitHub**, fill in exactly:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `markproof` |
   | Owner | `Tippel-AI` |
   | Repository name | `markproof` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   **Workflow name is the filename, not the path** — `release.yml`, not
   `.github/workflows/release.yml`.

4. Click **Add**.

Three things worth knowing:

- A pending publisher **reserves nothing**. The name `markproof` stays free for
  anyone else until your first successful upload converts the pending publisher
  into a normal one. If someone registers it first, the pending publisher is
  invalidated. That is an argument for releasing sooner rather than later.
- The environment field is optional on PyPI's side but *not* optional here: the
  workflow runs its publish job inside `environment: pypi`, so leaving the field
  empty makes every upload fail with `invalid-pending-publisher`.
- There is no token to create. No `PYPI_TOKEN` secret, no `~/.pypirc`, nothing to
  rotate or leak. If you catch yourself making one, something has gone wrong.

### 1.3 Open item before the first release

`NOTICE` promises a `THIRD_PARTY_LICENSES.md` that is "refreshed per release", and
that file does not exist yet. Either generate it (e.g. `uv run --extra dev
pip-licenses`-style inventory, committed) or soften the sentence in `NOTICE`.
Shipping a NOTICE that points at a missing file is the kind of small dishonesty
this project cannot afford.

---

## 2. Per release

Start on a clean `main` with CI green.

**1 — Close the changelog.** Move the `## [Unreleased]` entries into a version
section and give it a date:

```markdown
## [0.1.0] - 2026-09-05
```

The workflow reads that section verbatim and uses it as the GitHub release body. A
missing section stops the release; a heading that still says `unreleased` only
warns, but then the release notes carry that word into the world.

**2 — Bump the version.** `pyproject.toml` is the single source of truth;
`markproof.__version__` reads the installed metadata, so there is nothing else to
edit:

```toml
[project]
version = "0.1.0"   # the tree currently carries 0.1.0.dev0 — drop the .dev0
```

**3 — Commit it to `main`** the usual way (PR, CI green, merge).

**4 — Dry run.** Actions → **release** → **Run workflow** on `main`. Guard, lint,
types, tests, build and the clean-environment smoke install all run; nothing is
published, because both publishing jobs are gated on `github.ref_type == 'tag'`.
Two minutes now beats a half-published release later.

**5 — Tag and push.**

```sh
git switch main && git pull
git tag -a v0.1.0 -m "markproof 0.1.0"
git push origin v0.1.0
```

**6 — Watch the run** and approve the `pypi` deployment if you configured required
reviewers.

**7 — Verify from outside.**

```sh
uvx markproof@0.1.0 --version            # or: pipx install markproof==0.1.0
uvx markproof@0.1.0 rules list art50-eu-2026.07
```

Then open the GitHub release and check that the notes read like release notes.

**8 — Open the next cycle.** Bump `pyproject.toml` to the next `.dev0`, put an
empty `## [Unreleased]` section back at the top of the changelog, commit.

### What the workflow refuses to do

Worth knowing, because these are the ways it will stop you:

- publish when the tag and `pyproject.toml` name different versions
- publish when `CHANGELOG.md` has no section for the version being released
- publish when ruff, mypy or pytest fail on 3.11, 3.12 or 3.13
- publish a wheel it has not first installed into an empty environment and run
  (`markproof --version` and `rules list`, which also proves the packaged rulepacks
  actually travelled inside the wheel)

---

## 3. When it goes wrong

### The run failed before the upload

Nothing was published; the publish job is the last thing that happens. Delete the
tag, fix, tag again:

```sh
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0
```

This is safe **only** while nothing has reached PyPI. Never move a tag that already
published — the release on PyPI would then point at a commit that no longer exists.

### `invalid-publisher` or `invalid-pending-publisher`

The OIDC token is fine but matches no publisher: something differs between the four
values on PyPI and the four values in the workflow. Check all of them, including
capitalisation and typos:

| PyPI field | Where the other half lives |
|---|---|
| Owner | the GitHub organisation, `Tippel-AI` |
| Repository name | the repository name, `markproof` |
| Workflow name | the *filename* of `.github/workflows/release.yml` |
| Environment name | `environment: name:` in the `publish` job |

Renaming the repository, renaming or moving `release.yml`, or changing the
environment name all break publishing until PyPI is updated to match. This is also
why the workflow file carries that warning in its header comment.

### `Non-user identities cannot create new projects`

The pending publisher worked, but the **PyPI Project Name** you registered and the
`name` in `pyproject.toml` are not the same string. Both must be `markproof`.

### PyPI succeeded but the GitHub release failed

Re-run **only** the failed `github-release` job (Actions → the run → *Re-run failed
jobs*). Do not re-run the whole workflow: the publish job would try to upload files
that already exist and fail. If you have to do it by hand, download the `dist`
artifact from the run and:

```sh
gh release create v0.1.0 --title "markproof 0.1.0" --notes-file notes.md dist/*
```

### A broken version reached PyPI

This is the one that cannot be undone, so read before clicking. **A version number
on PyPI can never be uploaded twice** — deleting a release does not hand the number
back. Therefore:

1. **Yank it, do not delete it.** <https://pypi.org/manage/project/markproof/releases/>
   → *Options* → *Yank*, and give a reason; the reason is shown to users and in the
   index API. A yanked release is ignored by installers unless someone pins it
   exactly (`markproof==0.1.0`), so existing lockfiles keep resolving while nobody
   new picks it up ([PEP 592](https://peps.python.org/pep-0592/)).
2. Fix, bump to `0.1.1`, and go through section 2 again.
3. **Never delete the project.** Deleting a release burns that version number
   forever; deleting the *project* also releases the name `markproof` back into the
   pool, where anyone may register it
   ([PEP 541](https://docs.pypi.org/project-management/name-retention/)). Losing the
   name is a far worse day than a yanked release.

---

## 4. Maintaining the workflow

Every action in `release.yml` is pinned to an exact tag, verified against the
upstream tag list on 2026-08-31. Two traps when you bump them:

- **`astral-sh/setup-uv` publishes no major tag past `v7`.** `@v8`, `@v9` and `@v10`
  do not resolve; use the exact version, currently `v10.0.1`. This repository has
  already been bitten by it once.
- **`pypa/gh-action-pypi-publish` is documented upstream as `@release/v1`**, a
  moving branch. We pin `@v1.14.2` instead, so the identity that can upload to PyPI
  never changes without a commit. Check
  <https://github.com/pypa/gh-action-pypi-publish/releases> before a release and
  bump on purpose.

Verify any version before you commit it, rather than assuming a major tag exists:

```sh
gh api repos/astral-sh/setup-uv/tags --paginate --jq '.[].name' | head
```

### Why there is no TestPyPI step

A TestPyPI upload needs its own pending publisher and burns the version number
there as irreversibly as on PyPI, so it is a rehearsal you can only run once per
version. The dry run in step 4 and the clean-environment install of the real wheel
cover the same ground and can be repeated. If you ever do want one, add a second
publish job with `repository-url: https://test.pypi.org/legacy/` and register the
matching publisher on test.pypi.org.
