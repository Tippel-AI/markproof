# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Command line interface — the ``markproof`` entry point.

Planned commands (DEVELOPMENT_PLAN §5, M1/M4):

``run``
    Probe the configured target, evaluate the rulepack, write the report.
    Exit code 1 as soon as one finding is FAIL.
``verify-report``
    Re-canonicalise a ``report.json`` and check its Ed25519 signature against a
    public key — the auditor's workflow, deliberately a separate command.
``rules list`` / ``rules schema``
    List the rules of a rulepack; export the pydantic schemas as JSON Schema.
``init``
    Scaffold a ``markproof.yaml`` interactively.
``keygen``
    Generate an Ed25519 key pair for report signing.

The module-level object ``app`` is the console-script target declared in
``pyproject.toml`` (``markproof = "markproof.cli:app"``).
"""

# TODO(M0): app = typer.Typer(no_args_is_help=True) + `--version`.
# TODO(M1): run, rules list, rules schema.
# TODO(M4): verify-report, keygen, init; --json and --fail-on warn|fail flags.
