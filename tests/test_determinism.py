# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The determinism gate: identical evidence must produce identical bytes.

This is the claim the whole project rests on. A signed report is only worth
signing if the same inputs yield the same output — otherwise the signature
attests to a run, not to a verdict, and two people checking the same system get
two different documents.

For most of this repository's life the CI job named
``determinism (byte-identical report)`` ran three ``echo`` statements and went
green. A green check that verifies nothing is precisely the failure mode markproof
exists to catch in other people's systems, so it is worth saying plainly: the gate
below is the real one, and these tests are what that job now runs.

Two things are asserted per case:

* **Determinism** — the full pipeline, run twice over the same evidence, produces
  byte-identical canonical JSON.
* **Goldenness** — that output still matches the reviewed file on disk. A diff
  here is a change in the tool's judgement about what conformant means, and it is
  reviewed like code rather than refreshed away. Regenerate deliberately with
  ``pytest -m determinism --update-golden``.

The pipeline is reached through the same helpers the CLI uses, not a copy of
them. A gate that tested its own re-implementation would pass while shipped
reports changed shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from markproof.cli import _load_label_sets, _load_pattern_sets, _resolve_rulepack
from markproof.probes.base import Artifact, Evidence
from markproof.report.model import RunMetadata, build_report
from markproof.report.sign import report_from_dict
from markproof.rules.engine import combine, evaluate, probe_failure_finding
from markproof.rules.schema import Applicability, load_rulepack
from tests.golden.generate import FROZEN_RUN

pytestmark = pytest.mark.determinism

_GOLDEN = Path(__file__).resolve().parent / "golden"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _cases() -> list[Path]:
    return sorted(d for d in _GOLDEN.iterdir() if d.is_dir() and (d / "evidence.json").is_file())


def _evidence_with_bytes(raw: dict[str, Any]) -> Evidence:
    """Rebuild one Evidence, reattaching artefact bytes from the fixture corpus.

    ``Artifact.data`` is excluded from serialisation on purpose — evidence files
    stay diffable instead of carrying megabytes of base64 — so the golden case
    names a fixture path and the bytes are read back here. Without this the C2PA
    check would see no payload and report every asset as unreadable, and the gate
    would be testing an error path rather than a verdict.
    """
    turns = []
    for turn in raw["turns"]:
        artifacts = []
        for art in turn.get("artifacts", []):
            art = dict(art)
            fixture = art.pop("_fixture", None)
            artifacts.append(
                Artifact(**art, data=(_FIXTURES / fixture).read_bytes() if fixture else None)
            )
        turns.append({**turn, "artifacts": tuple(artifacts)})
    return Evidence.model_validate({**raw, "turns": tuple(turns)})


def _report_bytes(case: Path) -> str:
    """Run one golden case through the pipeline and canonicalise the result."""
    spec = json.loads((case / "evidence.json").read_text(encoding="utf-8"))

    rulepack = load_rulepack(_resolve_rulepack(spec["rulepack"]))
    evidences = [_evidence_with_bytes(e) for e in spec.get("evidences", [])]
    failures = [
        probe_failure_finding(f["probe_id"], f["reason"]) for f in spec.get("probe_failures", [])
    ]
    applicability = Applicability.model_validate(spec.get("applicability", {}))

    findings = combine(
        evaluate(
            rulepack,
            evidences,
            _load_pattern_sets(rulepack),
            None,
            _load_label_sets(rulepack),
            applicability,
        ),
        failures,
    )
    report = build_report(
        target=spec.get("target", "golden"),
        rulepack=rulepack,
        findings=findings,
        run=RunMetadata(**FROZEN_RUN),
        applicability=applicability,
    )
    # Exactly what the CLI writes, minus the signature — which is deterministic
    # over these bytes anyway, and pinning a key here would test Ed25519 rather
    # than markproof.
    return (
        json.dumps(report.model_dump(mode="json", exclude_none=True), indent=2, sort_keys=True)
        + "\n"
    )


class TestDeterminism:
    @pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
    def test_the_same_evidence_produces_the_same_bytes(self, case: Path) -> None:
        first, second = _report_bytes(case), _report_bytes(case)
        assert first == second, (
            f"{case.name}: two runs over identical evidence disagreed — a signed "
            "report attests to a run rather than a verdict if this ever fails"
        )

    @pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
    def test_the_report_still_matches_the_reviewed_golden(
        self, case: Path, request: pytest.FixtureRequest
    ) -> None:
        produced = _report_bytes(case)
        golden = case / "expected_report.json"

        if request.config.getoption("--update-golden"):
            golden.write_text(produced, encoding="utf-8")
            pytest.skip(f"golden updated: {case.name}")

        assert golden.is_file(), (
            f"{case.name} has no expected_report.json — generate it with "
            "`pytest -m determinism --update-golden` and review the diff"
        )
        assert produced == golden.read_text(encoding="utf-8"), (
            f"{case.name}: the verdict changed. This is a change in what the tool "
            "calls conformant — review it, do not refresh it away."
        )

    @pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
    def test_every_golden_report_can_be_read_back(self, case: Path) -> None:
        """A report a verifier cannot load is not evidence.

        This caught a real defect: ``guideline_ref`` was required-but-nullable, and
        writing with ``exclude_none=True`` dropped the key, so every report
        containing an unreachable-endpoint finding failed to load — the one case
        where the audit trail matters most.
        """
        report_from_dict(json.loads(_report_bytes(case)))


class TestTheGoldensCoverWhatMatters:
    def test_there_are_cases_at_all(self) -> None:
        assert _cases(), "the determinism gate has nothing to run"

    def test_a_failing_verdict_is_among_them(self) -> None:
        """A gate made only of passing cases would not notice a stuck PASS."""
        verdicts = {
            case.name: {f["result"] for f in json.loads(_report_bytes(case))["findings"]}
            for case in _cases()
        }
        assert any("FAIL" in v for v in verdicts.values()), verdicts
        assert any("PASS" in v for v in verdicts.values()), verdicts
        assert any("SKIP" in v for v in verdicts.values()), verdicts
        assert any("WARN" in v for v in verdicts.values()), verdicts

    def test_no_model_in_the_report_graph_is_required_but_nullable(self) -> None:
        """The shape that made reports unreadable, guarded structurally.

        A field typed ``X | None`` with no default round-trips only while its value
        is not None: ``exclude_none=True`` drops the key, and loading it back then
        fails with "field required". Either give it a default or make it required
        and non-nullable — never both.
        """
        from markproof.report.model import Report, RunMetadata, Signature, Summary
        from markproof.rules.engine import Finding

        offenders = []
        for model in (Report, RunMetadata, Summary, Signature, Finding):
            for name, field in model.model_fields.items():
                nullable = "None" in str(field.annotation)
                if nullable and field.is_required():
                    offenders.append(f"{model.__name__}.{name}")
        assert not offenders, (
            f"required-but-nullable fields break report round-tripping: {offenders}"
        )
