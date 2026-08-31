# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Command line interface — the ``markproof`` entry point.

``run``
    Probe the configured target, evaluate the rulepack, print the findings.
    Exit code 1 as soon as one finding is FAIL.
``rules list`` / ``rules schema``
    List the rules of a rulepack; export the pydantic schemas as JSON Schema.

``verify-report``, ``keygen`` and ``init`` arrive with the signed report in M4.

The module-level object ``app`` is the console-script target declared in
``pyproject.toml`` (``markproof = "markproof.cli:app"``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from markproof import __version__
from markproof.checks.disclosure import PatternSet, load_pattern_set
from markproof.config import ConfigError, MarkproofConfig, load_config
from markproof.probes.base import Evidence, ProbeError
from markproof.probes.http_chat import HttpChatProbe
from markproof.rules.engine import Finding, Result, evaluate, exit_code_for
from markproof.rules.schema import Rulepack, load_rulepack

__all__ = ["app"]

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Verify that a live AI endpoint still delivers marked, disclosed content.",
)
rules_app = typer.Typer(no_args_is_help=True, help="Inspect rulepacks.")
app.add_typer(rules_app, name="rules")

console = Console()
err_console = Console(stderr=True)

#: Packaged rulepacks and pattern files.
_RULEPACKS_DIR = Path(__file__).resolve().parent / "rulepacks"
_PATTERNS_DIR = Path(__file__).resolve().parent / "patterns"

#: Console colour per result — semantic, not decorative.
_RESULT_STYLE = {
    Result.PASS: "green",
    Result.FAIL: "bold red",
    Result.WARN: "yellow",
    Result.SKIP: "dim",
}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"markproof {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """markproof — Article 50 conformance checks for live endpoints."""


def _resolve_rulepack(name: str) -> Path:
    """Find a rulepack by id (packaged) or path (explicit file)."""
    candidate = Path(name)
    if candidate.is_file():
        return candidate
    packaged = _RULEPACKS_DIR / f"{name}.yaml"
    if packaged.is_file():
        return packaged
    available = sorted(p.stem for p in _RULEPACKS_DIR.glob("*.yaml"))
    raise ConfigError(
        f"rulepack {name!r} not found. Available: {', '.join(available) or 'none packaged'}"
    )


def _load_pattern_sets(rulepack: Rulepack) -> dict[str, PatternSet]:
    """Load every pattern file the rulepack references, once each."""
    sets: dict[str, PatternSet] = {}
    for rule in rulepack.rules:
        filename = getattr(rule.check, "patterns_file", None)
        if filename is None or filename in sets:
            continue
        path = _PATTERNS_DIR / filename
        if not path.is_file():
            raise ConfigError(f"rule {rule.id} references missing pattern file: {path}")
        sets[filename] = load_pattern_set(path)
    return sets


def _collect(config: MarkproofConfig) -> list[Evidence]:
    """Run every configured probe."""
    evidences: list[Evidence] = []
    for probe_config in config.target.probes:
        console.print(f"  probing [cyan]{probe_config.id}[/cyan] → {probe_config.url}")
        evidences.append(HttpChatProbe(probe_config).collect())
    return evidences


def _render(findings: list[Finding], target_name: str, rulepack: Rulepack) -> None:
    """Print the findings table and the summary line."""
    table = Table(box=None, pad_edge=False, show_edge=False)
    table.add_column("Rule", style="bold")
    table.add_column("Result")
    table.add_column("Probe", style="dim")
    table.add_column("Detail", overflow="fold")

    for finding in findings:
        table.add_row(
            finding.rule_id,
            f"[{_RESULT_STYLE[finding.result]}]{finding.result.value}[/]",
            finding.probe_id,
            finding.message,
        )

    console.print()
    console.print(
        f"  [bold]{target_name}[/bold] · rulepack {rulepack.rulepack} ({rulepack.version})"
    )
    console.print()
    console.print(table)
    console.print()

    counts = {r: sum(1 for f in findings if f.result is r) for r in Result}
    parts = [f"[{_RESULT_STYLE[r]}]{counts[r]} {r.value.lower()}[/]" for r in Result if counts[r]]
    console.print("  " + " · ".join(parts) if parts else "  no findings")
    console.print()


@app.command()
def run(
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to markproof.yaml.")
    ] = Path("markproof.yaml"),
    rulepack_name: Annotated[
        str | None,
        typer.Option("--rulepack", help="Override the rulepack named in the config."),
    ] = None,
    json_out: Annotated[
        Path | None,
        typer.Option("--json", help="Also write the findings as JSON to this path."),
    ] = None,
) -> None:
    """Probe the target and evaluate it against the rulepack."""
    try:
        config = load_config(config_path)
        rulepack = load_rulepack(_resolve_rulepack(rulepack_name or config.rulepack))
        pattern_sets = _load_pattern_sets(rulepack)
        evidences = _collect(config)
    except (ConfigError, ProbeError) as exc:
        err_console.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(code=2) from exc

    findings = evaluate(rulepack, evidences, pattern_sets)
    _render(findings, config.target.name, rulepack)

    if json_out is not None:
        payload = [f.model_dump(mode="json") for f in findings]
        json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        console.print(f"  findings written to [cyan]{json_out}[/cyan]")

    raise typer.Exit(code=exit_code_for(findings))


@rules_app.command("list")
def rules_list(
    rulepack_name: Annotated[str, typer.Argument(help="Rulepack id or path.")],
) -> None:
    """List the rules in a rulepack."""
    try:
        rulepack = load_rulepack(_resolve_rulepack(rulepack_name))
    except (ConfigError, ValueError) as exc:
        err_console.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(box=None, pad_edge=False, show_edge=False)
    table.add_column("Rule", style="bold")
    table.add_column("Article")
    table.add_column("Applies to", style="dim")
    table.add_column("Sev")
    table.add_column("Title", overflow="fold")

    for rule in sorted(rulepack.rules, key=lambda r: r.id):
        table.add_row(
            rule.id,
            rule.article,
            ", ".join(k.value for k in rule.applies_to),
            rule.severity.value,
            rule.title,
        )

    console.print()
    console.print(f"  [bold]{rulepack.rulepack}[/bold] {rulepack.version} · {rulepack.license}")
    console.print()
    console.print(table)
    console.print()
    console.print(f"  [dim]{rulepack.attribution.strip()}[/dim]")
    console.print()


@rules_app.command("schema")
def rules_schema() -> None:
    """Print the rulepack JSON Schema to stdout."""
    schema = Rulepack.model_json_schema()
    sys.stdout.write(json.dumps(schema, indent=2, sort_keys=True) + "\n")
