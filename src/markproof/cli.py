# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Command line interface — the ``markproof`` entry point.

``run``
    Probe the configured target, evaluate the rulepack, print the findings.
    Exit code 1 as soon as one finding is FAIL.
``rules list`` / ``rules schema``
    List the rules of a rulepack; export the pydantic schemas as JSON Schema.

``verify-report``
    Check a report's signature. The auditor's command: it needs the report, a
    public key and this tool, on a machine that never saw the system under test.
``keygen``
    Generate an Ed25519 key pair for signing.
``init``
    Write a starting ``markproof.yaml``.

The module-level object ``app`` is the console-script target declared in
``pyproject.toml`` (``markproof = "markproof.cli:app"``).
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from markproof import __version__
from markproof.checks.disclosure import PatternSet, load_pattern_set
from markproof.checks.labels import LabelPatternSet, load_label_set
from markproof.checks.synthid import WatermarkConfig, load_watermark_config
from markproof.config import (
    ConfigError,
    HttpChatProbeConfig,
    MarkproofConfig,
    MediaProbeConfig,
    ReportConfig,
    UiProbeConfig,
    load_config,
)
from markproof.probes.base import Evidence, ProbeError
from markproof.probes.http_chat import HttpChatProbe
from markproof.probes.media import MediaProbe
from markproof.probes.ui import UiProbe
from markproof.report.model import ProbeRecord, Report, build_report
from markproof.report.sign import (
    SigningError,
    generate_keypair,
    load_private_key,
    load_public_key,
    report_from_dict,
    sign_report,
    verify_report,
)
from markproof.report.summary import render_summary
from markproof.rules.engine import (
    ConfigurationRequiredError,
    Finding,
    Result,
    UnsupportedCheckError,
    combine,
    evaluate,
    exit_code_for,
    probe_failure_finding,
)
from markproof.rules.schema import Applicability, Rulepack, load_rulepack

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


def _signing_key(report_config: ReportConfig) -> str:
    """Where the signing key comes from, config first, environment second.

    ``report.sign_key`` was validated and then ignored, so an operator who wrote
    ``sign_key: env:CI_SIGNING_KEY`` in their config got an unsigned report and no
    hint why. The environment variable stays the fallback because that is what CI
    documentation everywhere assumes.
    """
    declared = (report_config.sign_key or "").strip()
    if declared.startswith("env:"):
        return os.environ.get(declared[4:], "").strip()
    if declared:
        return declared
    return os.environ.get("MARKPROOF_SIGNING_KEY", "").strip()


def _render_pdf(report: Report, path: Path, *, engine: str) -> None:
    """Write the PDF, or explain which extra is missing.

    Imported here rather than at module scope: both renderers are optional, and a
    top-level import would make the default output path — the one that must work
    on any runner — depend on a package the base install does not ship.
    """
    module = "pdf_reportlab" if engine == "pdf" else "pdf_weasy"
    extra = "pdf" if engine == "pdf" else "pdf-html"
    try:
        renderer = importlib.import_module(f"markproof.report.{module}")
        renderer.render_pdf(report, path)
    except Exception as exc:
        # Both renderers already raise their own well-worded unavailability error —
        # WeasyPrint's covers the case that actually bites people, where the wheel
        # is installed but ctypes cannot find Pango or cairo. Their message is
        # better than anything reconstructed here, so it is passed through and only
        # framed. Broad on purpose: whatever goes wrong producing an optional
        # artefact, the caller gets a sentence and exit 2, never a traceback.
        raise ConfigError(
            f"could not write the {engine} report: {exc}\n"
            f'  If the extra is missing: pip install "markproof[{extra}]"'
        ) from exc


def _readable(exc: Exception) -> str:
    """A sentence for a stranger, not a repr.

    ``KeyError`` stringifies to its quoted argument, so a missing pattern file
    would print as ``'disclosure.de-en.yaml'`` with no verb — accurate and
    useless. The SynthID case gets the install command attached, because "not
    available in this build" is only actionable if you know what to install.
    """
    text = exc.args[0] if exc.args else str(exc)
    message = str(text).strip()
    if "synthid" in message.lower() or "transformers" in message.lower():
        message += (
            "\n  Install the optional detector: pip install 'markproof[synthid]'\n"
            "  Or drop the text-marking rule from the rulepack if you do not watermark text."
        )
    return message


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


def _load_watermark(config: MarkproofConfig, config_path: Path) -> WatermarkConfig | None:
    """Load the operator's watermark config, resolved relative to markproof.yaml.

    Relative resolution matters: the path lives in a config file that is
    committed, while the file it points at usually is not.
    """
    if config.text_marking is None or config.text_marking.method != "synthid":
        return None
    raw = config.text_marking.watermark_config
    if raw is None:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = config_path.parent / path
    return load_watermark_config(path)


def _load_label_sets(rulepack: Rulepack) -> dict[str, LabelPatternSet]:
    """Load every label file the rulepack references, once each."""
    sets: dict[str, LabelPatternSet] = {}
    for rule in rulepack.rules:
        filename = getattr(rule.check, "labels_file", None)
        if filename is None or filename in sets:
            continue
        path = _PATTERNS_DIR / filename
        if not path.is_file():
            raise ConfigError(f"rule {rule.id} references missing label file: {path}")
        sets[filename] = load_label_set(path)
    return sets


def _collect(config: MarkproofConfig) -> tuple[list[Evidence], list[Finding]]:
    """Run every configured probe, collecting failures as findings.

    A probe that cannot reach its target does not abort the run: the other
    probes still have something to say, and the failure itself is a result worth
    recording. Aborting would also throw away the evidence that the check was
    attempted.
    """
    evidences: list[Evidence] = []
    failures: list[Finding] = []
    for probe_config in config.target.probes:
        console.print(f"  probing [cyan]{probe_config.id}[/cyan] → {probe_config.url}")
        try:
            # Explicit per type: an else-branch would quietly treat a probe
            # kind this build does not know as a chat probe.
            if isinstance(probe_config, MediaProbeConfig):
                evidences.append(MediaProbe(probe_config).collect())
            elif isinstance(probe_config, UiProbeConfig):
                evidences.append(UiProbe(probe_config).collect())
            elif isinstance(probe_config, HttpChatProbeConfig):
                evidences.append(HttpChatProbe(probe_config).collect())
            else:  # pragma: no cover - the config union makes this unreachable
                raise ConfigError(f"probe {probe_config.id!r} has a type this build cannot run")
        except ProbeError as exc:
            console.print(f"    [bold red]unreachable:[/] {exc}")
            failures.append(probe_failure_finding(probe_config.id, str(exc)))
    return evidences, failures


def _write_report(
    report_dir: Path,
    target: str,
    rulepack: Rulepack,
    findings: list[Finding],
    timestamp: str | None,
    applicability: Applicability,
    probes: tuple[ProbeRecord, ...],
    report_config: ReportConfig,
) -> None:
    """Write report.json and summary.md, signing when a key is configured.

    Signing is opt-in through MARKPROOF_SIGNING_KEY. An unsigned report is still
    a useful report — it is just not evidence someone else can check — so a
    missing key is a note, not an error.
    """
    report = build_report(
        target=target,
        rulepack=rulepack,
        findings=findings,
        timestamp=timestamp,
        applicability=applicability,
        probes=probes,
    )

    key_source = _signing_key(report_config)
    if key_source:
        try:
            report = sign_report(report, load_private_key(key_source))
        except SigningError as exc:
            # Never fall back to writing an unsigned report under a name the
            # caller asked to have signed: that would look like evidence.
            err_console.print(f"[bold red]signing failed:[/] {exc}")
            raise typer.Exit(code=2) from exc

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"
    summary_path = report_dir / "summary.md"

    formats = report_config.formats
    if "json" in formats:
        report_path.write_text(
            json.dumps(report.model_dump(mode="json", exclude_none=True), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        console.print(f"  report written to [cyan]{report_path}[/cyan]")
    if "summary" in formats:
        summary_path.write_text(render_summary(report), encoding="utf-8")
        console.print(f"  summary written to [cyan]{summary_path}[/cyan]")
    for fmt in ("pdf", "pdf-html"):
        if fmt in formats:
            pdf_path = report_dir / ("report.pdf" if fmt == "pdf" else "report-html.pdf")
            _render_pdf(report, pdf_path, engine=fmt)
            console.print(f"  {fmt} written to [cyan]{pdf_path}[/cyan]")
    if not key_source:
        console.print(
            "  [dim]unsigned — set MARKPROOF_SIGNING_KEY to produce verifiable evidence[/dim]"
        )


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

    out_of_scope = sorted(
        {
            f.obligation.value
            for f in findings
            if f.obligation is not None and f.detail.get("outcome") == "not_applicable"
        }
    )
    if out_of_scope:
        # Named on the console, not just in the report file: whoever is watching
        # the run has to see what their own configuration removed from it.
        console.print(f"  [dim]declared out of scope: {', '.join(out_of_scope)}[/dim]")
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
    report_dir: Annotated[
        Path | None,
        typer.Option(
            "--report-dir",
            help="Write report.json and summary.md here (signed if a key is set).",
        ),
    ] = None,
    timestamp: Annotated[
        str | None,
        typer.Option("--timestamp", help="Pin the report timestamp (ISO-8601). For tests."),
    ] = None,
) -> None:
    """Probe the target and evaluate it against the rulepack."""
    try:
        config = load_config(config_path)
        rulepack = load_rulepack(_resolve_rulepack(rulepack_name or config.rulepack))
        pattern_sets = _load_pattern_sets(rulepack)
        label_sets = _load_label_sets(rulepack)
        watermark = _load_watermark(config, config_path)
        evidences, probe_failures = _collect(config)
        findings = combine(
            evaluate(
                rulepack, evidences, pattern_sets, watermark, label_sets, config.applicability
            ),
            probe_failures,
        )
    except (ConfigError, SigningError, ValueError) as exc:
        # ValueError covers the watermark config loader, which validates a
        # user-supplied path — a wrong path is a configuration mistake and
        # deserves a sentence, not a traceback.
        err_console.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(code=2) from exc
    except (ConfigurationRequiredError, UnsupportedCheckError, KeyError) as exc:
        # Evaluation used to sit outside this block, so a rulepack asking for a
        # check this build cannot perform — the SynthID extra missing, most
        # commonly — reached the user as a traceback and exit 1. Exit 1 is this
        # tool's word for "a check failed". A pipeline could not tell "your
        # endpoint is not compliant" from "markproof fell over", which is exactly
        # the ambiguity probe_failure_finding() exists to prevent one layer down.
        err_console.print(f"[bold red]error:[/] {_readable(exc)}")
        raise typer.Exit(code=2) from exc
    _render(findings, config.target.name, rulepack)

    if json_out is not None:
        payload = [f.model_dump(mode="json") for f in findings]
        json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        console.print(f"  findings written to [cyan]{json_out}[/cyan]")

    destination = report_dir if report_dir is not None else None
    if destination is None and set(config.report.formats) - {"json", "summary"}:
        # An operator who asked for a PDF in the config meant it; falling through
        # to "no report at all" because they did not also pass --report-dir would
        # silently discard the request.
        destination = Path(config.report.output_dir)
    if destination is not None:
        # Guarded like the evaluation above, and for the same reason: producing an
        # optional artefact can fail — a missing extra, an unwritable directory —
        # and that is "the run could not finish", not "a rule failed". Exit 1 is
        # reserved for the second.
        try:
            _write_report(
                destination,
                config.target.name,
                rulepack,
                findings,
                timestamp,
                config.applicability,
                tuple(
                    ProbeRecord(id=p.id, kind=p.probe_kind.value, url=p.url)
                    for p in config.target.probes
                ),
                config.report,
            )
        except (ConfigError, OSError) as exc:
            err_console.print(f"[bold red]error:[/] {exc}")
            raise typer.Exit(code=2) from exc

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
    table.add_column("Obligation")
    table.add_column("Applies to", style="dim")
    table.add_column("Sev")
    table.add_column("Title", overflow="fold")

    for rule in sorted(rulepack.rules, key=lambda r: r.id):
        table.add_row(
            rule.id,
            rule.article,
            rule.obligation.value,
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


@app.command("verify-report")
def verify_report_command(
    report_path: Annotated[Path, typer.Argument(help="Path to report.json.")],
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Public key to verify against (PEM)."),
    ] = None,
) -> None:
    """Check a report's signature — the auditor's command.

    Deliberately separate from ``run``: verifying should need nothing but the
    report, a public key and this tool, on a machine that never saw the system
    under test.
    """
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as exc:
        err_console.print(f"[bold red]error:[/] cannot read {report_path}: {exc}")
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        err_console.print(f"[bold red]error:[/] {report_path} is not valid JSON: {exc}")
        raise typer.Exit(code=2) from exc

    try:
        report = report_from_dict(data)
        public_key = load_public_key(str(key)) if key is not None else None
    except SigningError as exc:
        err_console.print(f"[bold red]error:[/] {exc}")
        raise typer.Exit(code=2) from exc

    valid, message = verify_report(report, public_key)
    console.print()
    if valid:
        console.print(f"  [green]✓[/green] {message}")
    else:
        console.print(f"  [bold red]✗[/bold red] {message}")
    console.print(
        f"  [dim]{report.target} · {report.rulepack['id']} v{report.rulepack['version']} · "
        f"{report.run.timestamp}[/dim]"
    )
    console.print()
    raise typer.Exit(code=0 if valid else 1)


_SCAFFOLD = """\
# SPDX-License-Identifier: Apache-2.0
#
# Written by `markproof init`. Point it at the endpoint your users actually
# reach — a staging copy proves nothing about production.
version: 1

target:
  name: {name}
  probes:
    - id: chat
      type: http-chat
      url: {url}
      dialect: openai-chat        # or generic-json + response_path
      lang: de                    # de | en
      # auth: {{header: Authorization, env: MARKPROOF_TOKEN}}

# Which Article 50 obligations bind this target. Everything not listed is
# checked, so silence never removes a rule. A `false` here is a claim, not a mute
# switch: it travels into the signed report, so a green run states its own scope.
#
#   ai-interaction · synthetic-media-marking · synthetic-text-marking
#   emotion-recognition · deepfake-labelling · public-interest-text
# applicability:
#   deepfake-labelling: false

# Verifying text marking needs the parameters you generate with. Without them
# the text rule skips and says so — it never guesses.
# text_marking:
#   method: synthid
#   watermark_config: secrets/watermark_config.json

rulepack: art50-eu-2026.07

report:
  formats: [json, summary]        # add `pdf` for the artefact an auditor reads
  # sign_key: env:MARKPROOF_SIGNING_KEY
"""


@app.command()
def init(
    path: Annotated[Path, typer.Option("--config", "-c", help="Where to write the config.")] = Path(
        "markproof.yaml"
    ),
    url: Annotated[
        str,
        typer.Option("--url", help="The chat endpoint to probe."),
    ] = "https://api.example.com/v1/chat/completions",
    name: Annotated[str, typer.Option("--name", help="A name for the target.")] = "my-service",
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Write a starting markproof.yaml.

    Deliberately small. The scaffold configures one chat probe and leaves the
    media, UI and text-marking blocks commented out with the reason each is
    optional, because a config full of settings nobody chose is how people end up
    running checks they cannot interpret.
    """
    if path.exists() and not force:
        err_console.print(
            f"[bold red]error:[/] {path} already exists. Pass --force to overwrite it."
        )
        raise typer.Exit(code=2)

    try:
        path.write_text(_SCAFFOLD.format(name=name, url=url), encoding="utf-8")
    except OSError as exc:
        err_console.print(f"[bold red]error:[/] could not write {path}: {exc}")
        raise typer.Exit(code=2) from exc

    console.print()
    console.print(f"  wrote [cyan]{path}[/cyan]")
    console.print()
    console.print("  Next:")
    console.print(f"    1. set the url in {path} to the endpoint your users reach")
    console.print(f"    2. [cyan]markproof run --config {path}[/cyan]")
    console.print()
    console.print(
        "  [dim]No endpoint yet? examples/demo-bot is a deliberately non-conformant one.[/dim]"
    )
    console.print()


@app.command()
def keygen(
    out_dir: Annotated[
        Path, typer.Option("--out-dir", help="Where to write the key pair.")
    ] = Path(),
) -> None:
    """Generate an Ed25519 key pair for report signing."""
    private_path, public_path = generate_keypair(out_dir)
    console.print()
    console.print(f"  private key  [cyan]{private_path}[/cyan]  [dim](mode 600)[/dim]")
    console.print(f"  public key   [cyan]{public_path}[/cyan]")
    console.print()
    console.print("  [yellow]Keep the private key out of version control.[/yellow]")
    console.print("  In CI, put its contents in a secret and expose it as")
    console.print("  [cyan]MARKPROOF_SIGNING_KEY[/cyan]. Share the public key freely —")
    console.print("  anyone verifying a report needs it.")
    console.print()


if __name__ == "__main__":  # pragma: no cover - module execution entry point
    # `python -m markproof.cli` has to work, not just the installed console
    # script: CI images, containers and one-off debugging all reach for it, and
    # without this the module runs and exits 0 having done nothing at all.
    app()
