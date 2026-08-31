# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Failure paths — the ones that must never look like success.

Every test here guards the same property from a different angle: a check that
could not be performed must not produce a green build. "The endpoint was
unreachable" and "the endpoint is compliant" are opposite results, and a report
that renders them alike is worse than no report.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from markproof.config import ConfigError, HttpChatProbeConfig, load_config
from markproof.probes.base import ProbeError
from markproof.probes.http_chat import HttpChatProbe
from markproof.rules.engine import (
    OPERATIONAL_RULE_ID,
    Result,
    exit_code_for,
    probe_failure_finding,
)

_URL = "https://api.example.invalid/v1/chat/completions"


def _chat_config(**kwargs: object) -> HttpChatProbeConfig:
    base: dict[str, object] = {"id": "chat", "type": "http-chat", "url": _URL, "lang": "de"}
    base.update(kwargs)
    return HttpChatProbeConfig(**base)  # type: ignore[arg-type]


class TestProbeFailureFinding:
    def test_a_failed_probe_blocks_the_build(self) -> None:
        finding = probe_failure_finding("chat", "connection refused")
        assert finding.result is Result.FAIL
        assert exit_code_for([finding]) == 1

    def test_it_is_not_a_skip(self) -> None:
        """A skip would let the pipeline go green over an unchecked system."""
        assert probe_failure_finding("chat", "timeout").result is not Result.SKIP

    def test_the_reason_survives_into_the_finding(self) -> None:
        finding = probe_failure_finding("chat", "TLS handshake failed")
        assert "TLS handshake failed" in finding.message


class TestTransportFailures:
    """Every way a probe can fail must become a ProbeError, never a traceback."""

    @respx.mock
    def test_connection_refused(self) -> None:
        respx.post(_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(ProbeError, match="unreachable"):
            HttpChatProbe(_chat_config()).collect()

    @respx.mock
    def test_timeout(self) -> None:
        respx.post(_URL).mock(side_effect=httpx.ReadTimeout("too slow"))
        with pytest.raises(ProbeError, match="unreachable"):
            HttpChatProbe(_chat_config()).collect()

    @respx.mock
    def test_tls_failure(self) -> None:
        respx.post(_URL).mock(side_effect=httpx.ConnectError("certificate verify failed"))
        with pytest.raises(ProbeError, match="unreachable"):
            HttpChatProbe(_chat_config()).collect()

    @pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
    @respx.mock
    def test_http_error_statuses_name_the_code(self, status: int) -> None:
        respx.post(_URL).mock(return_value=httpx.Response(status, json={"error": "no"}))
        with pytest.raises(ProbeError, match=str(status)):
            HttpChatProbe(_chat_config()).collect()

    @respx.mock
    def test_html_error_page_with_status_200(self) -> None:
        """A proxy returning its own page is not a model answering."""
        respx.post(_URL).mock(return_value=httpx.Response(200, content=b"<html>oops</html>"))
        with pytest.raises(ProbeError, match="not JSON"):
            HttpChatProbe(_chat_config()).collect()

    @respx.mock
    def test_json_without_the_expected_shape(self) -> None:
        respx.post(_URL).mock(return_value=httpx.Response(200, json={"unexpected": True}))
        with pytest.raises(ProbeError, match="response path"):
            HttpChatProbe(_chat_config()).collect()

    @respx.mock
    def test_content_that_is_not_a_string(self) -> None:
        respx.post(_URL).mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": {"nested": "object"}}}]}
            )
        )
        with pytest.raises(ProbeError, match="expected a string"):
            HttpChatProbe(_chat_config()).collect()


class TestConfigErrors:
    """Operator mistakes are reported as mistakes, not as findings."""

    def test_missing_file_names_the_path(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "absent.yaml")

    def test_malformed_yaml_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("version: 1\n  bad indent: [", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(path)

    def test_unknown_probe_type_is_rejected(self, tmp_path: Path) -> None:
        """Never silently ignore a probe block the build cannot run."""
        path = tmp_path / "c.yaml"
        path.write_text(
            "version: 1\n"
            "target:\n  name: t\n  probes:\n"
            "    - id: x\n      type: telepathy\n      url: https://e.invalid\n"
            "rulepack: art50-eu-2026.07\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError):
            load_config(path)

    def test_missing_auth_env_var_names_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from markproof.config import AuthConfig

        monkeypatch.delenv("MARKPROOF_TEST_TOKEN", raising=False)
        with pytest.raises(ConfigError, match="MARKPROOF_TEST_TOKEN"):
            AuthConfig(env="MARKPROOF_TEST_TOKEN").resolve()


class TestCliBehaviour:
    """The observable contract: exit codes and artefacts."""

    @staticmethod
    def _run(config: Path, report_dir: Path) -> subprocess.CompletedProcess[str]:
        # The command is built entirely from sys.executable and paths this test
        # created; nothing here comes from outside.
        return subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "markproof.cli",
                "run",
                "-c",
                str(config),
                "--report-dir",
                str(report_dir),
                "--timestamp",
                "2026-08-31T12:00:00+00:00",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    @pytest.fixture
    def unreachable_config(self, tmp_path: Path) -> Path:
        path = tmp_path / "markproof.yaml"
        path.write_text(
            "version: 1\n"
            "target:\n  name: unreachable\n  probes:\n"
            "    - id: chat\n      type: http-chat\n"
            "      url: http://127.0.0.1:9/v1/chat/completions\n      lang: de\n"
            "rulepack: art50-eu-2026.07\n",
            encoding="utf-8",
        )
        return path

    def test_unreachable_endpoint_exits_one_not_two(
        self, unreachable_config: Path, tmp_path: Path
    ) -> None:
        """Exit 1 is a verdict; exit 2 would say the tool could not be used."""
        result = self._run(unreachable_config, tmp_path / "report")
        assert result.returncode == 1

    def test_unreachable_endpoint_still_writes_evidence(
        self, unreachable_config: Path, tmp_path: Path
    ) -> None:
        """Proof that the check was attempted is worth more than no file."""
        report_dir = tmp_path / "report"
        self._run(unreachable_config, report_dir)
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        rule_ids = {f["rule_id"] for f in report["findings"]}
        assert OPERATIONAL_RULE_ID in rule_ids
        assert report["summary"]["failed"] >= 1
        assert (
            not (report_dir / "summary.md")
            .read_text(encoding="utf-8")
            .startswith("## markproof — unreachable\n\n**All")
        )

    def test_config_error_exits_two_and_writes_nothing(self, tmp_path: Path) -> None:
        """An unusable config is an operator mistake, not a finding about a system."""
        missing = tmp_path / "absent.yaml"
        report_dir = tmp_path / "report"
        result = self._run(missing, report_dir)
        assert result.returncode == 2
        assert not report_dir.exists()
