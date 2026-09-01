# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The command line, which is the whole product for almost everyone.

This file exists because `cli.py` sat at 21% coverage while the library around it
was near 90%. The aggregate looked healthy; the distribution was the problem. What
was unprotected is exactly what a pipeline depends on:

* **Exit codes.** This tool assigns them meaning — 0 nothing blocking, 1 a rule
  failed, 2 the run could not be performed. A regression there is invisible in
  every other test and changes what every adopter's CI concludes.
* **Failure paths.** A stranger's first contact with a compliance tool is often a
  mistake they made, and a traceback answers "is my endpoint compliant?" with a
  stack frame.
* **The signing guard.** Refusing to write an unsigned report under a name the
  caller asked to have signed is a security property, and nothing exercised it.
"""

from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from markproof.cli import app

RUNNER = CliRunner()

#: The PDF path needs an optional extra. CI installs it so the path is genuinely
#: covered; a contributor without it gets a skip rather than a puzzling failure.
needs_reportlab = pytest.mark.skipif(
    importlib.util.find_spec("reportlab") is None,
    reason="needs the [pdf] extra: pip install 'markproof[pdf]'",
)

_ENDPOINT = "https://api.example.invalid/v1/chat/completions"
_DISCLOSED = "Hallo! Sie sprechen mit einer KI. Wie kann ich helfen?"
_SILENT = "Hallo! Wie kann ich Ihnen helfen?"


def _config(tmp_path: Path, *, url: str = _ENDPOINT, extra: str = "") -> Path:
    path = tmp_path / "markproof.yaml"
    path.write_text(
        "version: 1\n"
        "target:\n"
        "  name: test-target\n"
        "  probes:\n"
        "    - id: chat\n"
        "      type: http-chat\n"
        f"      url: {url}\n"
        "      lang: de\n"
        "rulepack: art50-eu-2026.07\n" + extra,
        encoding="utf-8",
    )
    return path


def _reply(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "demo",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
        },
    )


@pytest.fixture(autouse=True)
def _no_stray_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every CLI test in its own directory.

    The report is written to `report.output_dir` by default, which is relative —
    so without this the suite quietly deposits `markproof-report/` in whatever
    directory pytest happened to start in. It did, once.
    """
    monkeypatch.chdir(tmp_path)


class TestExitCodes:
    """The contract every adopter's pipeline is written against."""

    @respx.mock
    def test_a_conformant_endpoint_exits_zero(self, tmp_path: Path) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path))])
        assert result.exit_code == 0, result.output

    @respx.mock
    def test_a_failing_rule_exits_one(self, tmp_path: Path) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_SILENT))
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path))])
        assert result.exit_code == 1, result.output
        assert "MPF-D-001" in result.output

    def test_a_run_that_could_not_happen_exits_two(self, tmp_path: Path) -> None:
        """Distinct from 1 on purpose: "not checked" must never look like "failed"."""
        result = RUNNER.invoke(app, ["run", "-c", str(tmp_path / "absent.yaml")])
        assert result.exit_code == 2
        assert "not found" in result.output.lower()

    @respx.mock
    def test_an_unreachable_endpoint_fails_rather_than_passing_quietly(
        self, tmp_path: Path
    ) -> None:
        """The worst possible outcome for this tool is a green run that checked nothing."""
        respx.post(_ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path))])
        assert result.exit_code == 1, result.output
        assert "MPF-X-001" in result.output


class TestFailurePathsSpeakInSentences:
    """No stack traces. A traceback answers the compliance question with a stack frame."""

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "markproof.yaml"
        bad.write_text("version: 1\ntarget: [unclosed\n", encoding="utf-8")
        result = RUNNER.invoke(app, ["run", "-c", str(bad)])
        assert result.exit_code == 2
        assert "Traceback" not in result.output

    def test_a_config_that_is_not_a_mapping(self, tmp_path: Path) -> None:
        bad = tmp_path / "markproof.yaml"
        bad.write_text("- just\n- a list\n", encoding="utf-8")
        result = RUNNER.invoke(app, ["run", "-c", str(bad)])
        assert result.exit_code == 2
        assert "mapping" in result.output.lower()

    def test_an_unknown_rulepack_lists_what_is_available(self, tmp_path: Path) -> None:
        result = RUNNER.invoke(
            app, ["run", "-c", str(_config(tmp_path)), "--rulepack", "no-such-pack"]
        )
        assert result.exit_code == 2
        assert "art50-eu-2026.07" in result.output, "the error should name a pack that exists"

    @respx.mock
    def test_a_check_this_build_cannot_perform_is_not_a_traceback(self, tmp_path: Path) -> None:
        """Issue #22: evaluation used to sit outside the guarded block.

        A rulepack asking for an unimplemented check reached the user as a
        traceback and exit 1 — and exit 1 is this tool's word for "a rule failed".
        A pipeline could not tell a non-compliant endpoint from a broken tool.
        """
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        pack = tmp_path / "future.yaml"
        packaged = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "markproof"
            / "rulepacks"
            / "art50-eu-2026.07.yaml"
        )
        pack.write_text(
            packaged.read_text(encoding="utf-8").replace(
                "type: disclosure-pattern", "type: disclosure-pattern"
            ),
            encoding="utf-8",
        )
        # A pattern file the loader cannot find is the same class of failure and
        # needs no future check type to provoke.
        pack.write_text(
            pack.read_text(encoding="utf-8").replace(
                "patterns_file: disclosure.de-en.yaml",
                "patterns_file: not-shipped.yaml",
            ),
            encoding="utf-8",
        )
        renamed = tmp_path / "art50-eu-2026.07.yaml"
        pack.rename(renamed)
        result = RUNNER.invoke(
            app, ["run", "-c", str(_config(tmp_path)), "--rulepack", str(renamed)]
        )
        assert "Traceback" not in result.output, result.output
        assert result.exit_code == 2, (
            f"a run that could not happen must not exit 1: {result.output}"
        )


class TestReportWriting:
    @respx.mock
    def test_the_report_is_written_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The report is the deliverable, so it is not opt-in.

        `markproof init` then `markproof run` used to print a table and produce
        nothing, which for a tool whose pitch is "hand someone else the
        measurement" is the wrong first experience.
        """
        monkeypatch.chdir(tmp_path)
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path))])
        assert (tmp_path / "markproof-report" / "report.json").is_file()

    @respx.mock
    def test_no_report_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--no-report"])
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "markproof-report").exists()

    @respx.mock
    def test_output_dir_from_the_config_is_honoured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        config = _config(tmp_path, extra="report:\n  output_dir: evidence\n")
        RUNNER.invoke(app, ["run", "-c", str(config)])
        assert (tmp_path / "evidence" / "report.json").is_file()

    @respx.mock
    def test_report_dir_writes_both_files(self, tmp_path: Path) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        out = tmp_path / "out"
        RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--report-dir", str(out)])
        assert (out / "report.json").is_file()
        assert (out / "summary.md").is_file()

    @respx.mock
    def test_the_report_names_the_endpoint_and_pins_the_rulepack(self, tmp_path: Path) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        out = tmp_path / "out"
        RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--report-dir", str(out)])
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        assert report["probes"][0]["url"] == _ENDPOINT
        assert len(report["rulepack"]["sha256"]) == 64

    @respx.mock
    def test_json_findings_are_written_when_asked(self, tmp_path: Path) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_SILENT))
        out = tmp_path / "findings.json"
        RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--json", str(out)])
        findings = json.loads(out.read_text(encoding="utf-8"))
        assert any(f["result"] == "FAIL" for f in findings)


class TestSigning:
    """The guard nothing exercised: never write an unsigned file under a signed name."""

    @respx.mock
    def test_a_valid_key_produces_a_signed_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        keys = tmp_path / "keys"
        keys.mkdir()
        RUNNER.invoke(app, ["keygen", "--out-dir", str(keys)])
        private = keys / "markproof-signing-key.pem"
        monkeypatch.setenv("MARKPROOF_SIGNING_KEY", private.read_text(encoding="utf-8"))

        out = tmp_path / "out"
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--report-dir", str(out)])
        assert result.exit_code == 0, result.output
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        assert report["signature"]["algorithm"] == "Ed25519"

        public = keys / "markproof-public-key.pem"
        verified = RUNNER.invoke(
            app, ["verify-report", str(out / "report.json"), "--key", str(public)]
        )
        assert verified.exit_code == 0, verified.output

    @respx.mock
    def test_a_broken_key_writes_nothing_at_all(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unsigned file where a signed one was asked for would look like evidence."""
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        monkeypatch.setenv("MARKPROOF_SIGNING_KEY", "-----BEGIN PRIVATE KEY-----\nnope\n")
        out = tmp_path / "out"
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--report-dir", str(out)])
        assert result.exit_code == 2, result.output
        assert not (out / "report.json").exists(), "a report was written despite signing failing"


class TestVerifyReport:
    """The auditor's command: nothing but a file, a key and this tool."""

    def _signed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        keys = tmp_path / "keys"
        keys.mkdir()
        RUNNER.invoke(app, ["keygen", "--out-dir", str(keys)])
        monkeypatch.setenv(
            "MARKPROOF_SIGNING_KEY",
            (keys / "markproof-signing-key.pem").read_text(encoding="utf-8"),
        )
        out = tmp_path / "out"
        with respx.mock:
            respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
            RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path)), "--report-dir", str(out)])
        return out / "report.json", keys / "markproof-public-key.pem"

    def test_a_tampered_verdict_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report_path, public = self._signed(tmp_path, monkeypatch)
        data = json.loads(report_path.read_text(encoding="utf-8"))
        # Downgrade a real verdict rather than rewriting a PASS to a PASS: the
        # point is that changing what the report says breaks the signature, and a
        # no-op edit would pass this test while proving nothing.
        assert data["summary"]["passed"] > 0
        data["summary"]["passed"] = 99
        data["target"] = "somebody-elses-system"
        report_path.write_text(json.dumps(data), encoding="utf-8")
        result = RUNNER.invoke(app, ["verify-report", str(report_path), "--key", str(public)])
        assert result.exit_code == 1
        assert "✗" in result.output

    def test_a_file_that_is_not_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "report.json"
        bad.write_text("not json", encoding="utf-8")
        result = RUNNER.invoke(app, ["verify-report", str(bad)])
        assert result.exit_code == 2
        assert "Traceback" not in result.output

    def test_a_missing_file(self, tmp_path: Path) -> None:
        result = RUNNER.invoke(app, ["verify-report", str(tmp_path / "gone.json")])
        assert result.exit_code == 2
        assert "Traceback" not in result.output


class TestKeygen:
    def test_the_private_key_is_not_readable_by_anyone_else(self, tmp_path: Path) -> None:
        result = RUNNER.invoke(app, ["keygen", "--out-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        private = tmp_path / "markproof-signing-key.pem"
        mode = private.stat().st_mode
        assert not mode & (stat.S_IRWXG | stat.S_IRWXO), oct(mode & 0o777)

    def test_it_says_what_to_do_with_the_keys(self, tmp_path: Path) -> None:
        result = RUNNER.invoke(app, ["keygen", "--out-dir", str(tmp_path)])
        assert "MARKPROOF_SIGNING_KEY" in result.output


class TestInspection:
    def test_rules_list_shows_the_shipped_pack(self) -> None:
        result = RUNNER.invoke(app, ["rules", "list", "art50-eu-2026.07"])
        assert result.exit_code == 0
        assert "MPF-D-001" in result.output
        assert "European Commission" in result.output, "the CC-BY credit must travel"

    def test_rules_list_on_an_unknown_pack_is_a_sentence(self) -> None:
        result = RUNNER.invoke(app, ["rules", "list", "nope"])
        assert result.exit_code == 2
        assert "Traceback" not in result.output

    def test_rules_schema_is_valid_json_schema(self) -> None:
        result = RUNNER.invoke(app, ["rules", "schema"])
        assert result.exit_code == 0
        schema = json.loads(result.stdout)
        assert schema["title"] == "Rulepack"

    def test_version_is_reported(self) -> None:
        from markproof import __version__

        result = RUNNER.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestTimestampPinning:
    @respx.mock
    def test_the_timestamp_can_be_pinned(self, tmp_path: Path) -> None:
        """Needed by anyone reproducing a report, not only by our own tests."""
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        out = tmp_path / "out"
        stamp = "2026-08-31T12:00:00+00:00"
        RUNNER.invoke(
            app,
            ["run", "-c", str(_config(tmp_path)), "--report-dir", str(out), "--timestamp", stamp],
        )
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        assert report["run"]["timestamp"] == stamp


class TestPdfOutput:
    """Issue #21: 354 lines of renderer that no invocation could reach.

    `ReportConfig.formats` was typed to accept only json and summary, the CLI
    never imported either renderer, and `run --help` said nothing about PDF — while
    the README advertised `pip install "markproof[pdf]"` as if installing the extra
    got you one. The PDF is the artefact you hand an auditor, so having it exist
    only in the source tree was the gap least likely to be noticed and most likely
    to matter.
    """

    @needs_reportlab
    @respx.mock
    def test_a_pdf_is_written_when_the_config_asks_for_one(self, tmp_path: Path) -> None:
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        config = _config(tmp_path, extra="report:\n  formats: [json, pdf]\n")
        out = tmp_path / "out"
        result = RUNNER.invoke(app, ["run", "-c", str(config), "--report-dir", str(out)])
        assert result.exit_code == 0, result.output
        pdf = out / "report.pdf"
        assert pdf.is_file()
        assert pdf.read_bytes().startswith(b"%PDF-"), "not a PDF"

    @respx.mock
    def test_formats_are_honoured_rather_than_validated_and_ignored(self, tmp_path: Path) -> None:
        """Asking for json alone must not also produce a summary."""
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        config = _config(tmp_path, extra="report:\n  formats: [json]\n")
        out = tmp_path / "out"
        RUNNER.invoke(app, ["run", "-c", str(config), "--report-dir", str(out)])
        assert (out / "report.json").is_file()
        assert not (out / "summary.md").exists()

    @needs_reportlab
    @respx.mock
    def test_a_pdf_request_alone_is_enough_to_write_a_report(self, tmp_path: Path) -> None:
        """Without --report-dir, output_dir from the config is used.

        An operator who asked for a PDF meant it; producing nothing because they
        did not also pass a flag would discard the request silently.
        """
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        config = _config(
            tmp_path, extra=f"report:\n  formats: [pdf]\n  output_dir: {tmp_path / 'declared'}\n"
        )
        RUNNER.invoke(app, ["run", "-c", str(config)])
        assert (tmp_path / "declared" / "report.pdf").is_file()

    @respx.mock
    def test_a_missing_extra_is_a_sentence_with_the_install_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pdf-html needs Pango and cairo, which pip cannot install for you."""
        from markproof.report import pdf_weasy

        def _unavailable(*_: object, **__: object) -> None:
            raise pdf_weasy.WeasyPrintUnavailableError(
                "WeasyPrint is not installed. pip install 'markproof[pdf-html]' — "
                "it also needs Pango and cairo, which pip does not install."
            )

        monkeypatch.setattr(pdf_weasy, "render_pdf", _unavailable)
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        config = _config(tmp_path, extra="report:\n  formats: [pdf-html]\n")
        result = RUNNER.invoke(
            app, ["run", "-c", str(config), "--report-dir", str(tmp_path / "out")]
        )
        assert result.exit_code == 2, result.output
        assert "Traceback" not in result.output
        assert "pdf-html" in result.output


class TestSignKeyFromConfig:
    @respx.mock
    def test_the_config_can_name_the_environment_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`sign_key` was validated and then ignored, so a report went out unsigned."""
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        keys = tmp_path / "keys"
        keys.mkdir()
        RUNNER.invoke(app, ["keygen", "--out-dir", str(keys)])
        monkeypatch.setenv(
            "CI_SIGNING_KEY", (keys / "markproof-signing-key.pem").read_text(encoding="utf-8")
        )
        monkeypatch.delenv("MARKPROOF_SIGNING_KEY", raising=False)

        config = _config(tmp_path, extra="report:\n  sign_key: env:CI_SIGNING_KEY\n")
        out = tmp_path / "out"
        result = RUNNER.invoke(app, ["run", "-c", str(config), "--report-dir", str(out)])
        assert result.exit_code == 0, result.output
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        assert "signature" in report, "the configured key was ignored"


class TestInit:
    """The command the module docstring promised and the build did not have.

    A promised-but-absent command is worse than no command: it tells a reader the
    documentation is not checked against the code, which for a tool selling
    verification is the wrong first impression.
    """

    def test_it_writes_a_config_that_actually_loads(self, tmp_path: Path) -> None:
        """A scaffold that fails validation would be worse than none at all."""
        from markproof.config import load_config

        target = tmp_path / "markproof.yaml"
        result = RUNNER.invoke(app, ["init", "--config", str(target)])
        assert result.exit_code == 0, result.output
        config = load_config(target)
        assert config.target.probes
        assert config.rulepack == "art50-eu-2026.07"

    def test_the_rulepack_it_names_is_one_that_ships(self, tmp_path: Path) -> None:
        from markproof.config import load_config

        target = tmp_path / "markproof.yaml"
        RUNNER.invoke(app, ["init", "--config", str(target)])
        packaged = Path(__file__).resolve().parent.parent / "src" / "markproof" / "rulepacks"
        assert (packaged / f"{load_config(target).rulepack}.yaml").is_file()

    def test_it_refuses_to_clobber_an_existing_config(self, tmp_path: Path) -> None:
        target = tmp_path / "markproof.yaml"
        target.write_text("version: 1\n# hand-written\n", encoding="utf-8")
        result = RUNNER.invoke(app, ["init", "--config", str(target)])
        assert result.exit_code == 2
        assert "hand-written" in target.read_text(encoding="utf-8")

    def test_force_overwrites(self, tmp_path: Path) -> None:
        target = tmp_path / "markproof.yaml"
        target.write_text("old\n", encoding="utf-8")
        result = RUNNER.invoke(app, ["init", "--config", str(target), "--force"])
        assert result.exit_code == 0
        assert "old" not in target.read_text(encoding="utf-8")

    def test_the_url_and_name_reach_the_file(self, tmp_path: Path) -> None:
        from markproof.config import load_config

        target = tmp_path / "markproof.yaml"
        RUNNER.invoke(
            app,
            ["init", "--config", str(target), "--url", "https://x.test/v1/c", "--name", "prod-bot"],
        )
        config = load_config(target)
        assert config.target.name == "prod-bot"
        assert config.target.probes[0].url == "https://x.test/v1/c"

    def test_it_points_somewhere_a_newcomer_can_actually_go(self, tmp_path: Path) -> None:
        result = RUNNER.invoke(app, ["init", "--config", str(tmp_path / "markproof.yaml")])
        assert "demo-bot" in result.output, (
            "a first-time user with no endpoint of their own needs somewhere to point this"
        )


class TestTheTerminalPrintsWhatItMeans:
    """Rich reads square brackets as markup, and every extras hint had them.

    `pip install 'markproof[synthid]'` reached the user as `pip install
    'markproof'` — a command that installs the base package and does not fix the
    problem they just hit. The same swallowing applies to any finding message or
    identifier containing brackets, because table cells are markup too.
    """

    @respx.mock
    def test_a_missing_extra_prints_an_install_command_that_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from markproof.report import pdf_weasy

        def _unavailable(*_: object, **__: object) -> None:
            raise pdf_weasy.WeasyPrintUnavailableError("WeasyPrint is not installed.")

        monkeypatch.setattr(pdf_weasy, "render_pdf", _unavailable)
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        config = _config(tmp_path, extra="report:\n  formats: [pdf-html]\n")
        result = RUNNER.invoke(
            app, ["run", "-c", str(config), "--report-dir", str(tmp_path / "out")]
        )
        assert "markproof[pdf-html]" in result.output, (
            f"the extra was swallowed by markup: {result.output!r}"
        )

    @respx.mock
    def test_a_finding_message_with_brackets_survives_the_table(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Messages are data. A rulepack author's wording must reach the reader."""
        from markproof.rules import engine

        real = engine.evaluate

        def _bracketed(*args: object, **kwargs: object) -> list[engine.Finding]:
            findings = real(*args, **kwargs)  # type: ignore[arg-type]
            return [
                f.model_copy(update={"message": "see [section 4] of the guidelines"})
                for f in findings
            ]

        monkeypatch.setattr("markproof.cli.evaluate", _bracketed)
        respx.post(_ENDPOINT).mock(return_value=_reply(_DISCLOSED))
        result = RUNNER.invoke(app, ["run", "-c", str(_config(tmp_path))])
        assert "[section 4]" in result.output, result.output

    def test_rules_list_does_not_eat_a_bracketed_title(self) -> None:
        result = RUNNER.invoke(app, ["rules", "list", "art50-eu-2026.07"])
        assert result.exit_code == 0
        # The shipped attribution contains "(EU) 2024/1689" and bracketed clause
        # references; none of it may vanish.
        assert "2024/1689" in result.output
