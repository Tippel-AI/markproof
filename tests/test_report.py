# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Report building, canonicalisation, signing and verification.

The signature is the product here: everything below asks whether it means what
it claims. A signature that survives a tampered document, or one that breaks on
a reformatted-but-identical document, would both be worse than none.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from markproof.report.model import Report, build_report
from markproof.report.sign import (
    SigningError,
    canonicalise,
    generate_keypair,
    load_private_key,
    load_public_key,
    report_from_dict,
    sign_report,
    verify_report,
)
from markproof.report.summary import render_summary
from markproof.rules.engine import Finding, Result
from markproof.rules.schema import Obligation, Rulepack, load_rulepack

_TIMESTAMP = "2026-08-31T12:00:00+00:00"


def _finding(rule_id: str = "MPF-D-001", result: Result = Result.FAIL) -> Finding:
    return Finding(
        rule_id=rule_id,
        title="AI disclosure before first interaction",
        article="Art. 50(1)",
        guideline_ref="Guidelines §3.2",
        probe_id="chat",
        result=result,
        message="no AI disclosure found",
        detail={"outcome": "not_disclosed", "lang": "de"},
        evidence_sha256=("ab" * 32,),
    )


@pytest.fixture
def report(rulepack: Rulepack) -> Report:
    return build_report(
        target="demo-bot",
        rulepack=rulepack,
        findings=[_finding()],
        timestamp=_TIMESTAMP,
    )


@pytest.fixture
def keys(tmp_path: Path) -> tuple[Path, Path]:
    return generate_keypair(tmp_path / "keys")


class TestBuilding:
    def test_summary_counts_every_result(self, rulepack: Rulepack) -> None:
        findings = [
            _finding("MPF-D-001", Result.PASS),
            _finding("MPF-D-002", Result.FAIL),
            _finding("MPF-D-003", Result.WARN),
            _finding("MPF-M-001", Result.SKIP),
        ]
        report = build_report(
            target="t", rulepack=rulepack, findings=findings, timestamp=_TIMESTAMP
        )
        assert (report.summary.passed, report.summary.failed) == (1, 1)
        assert (report.summary.warned, report.summary.skipped) == (1, 1)
        assert report.summary.total == 4
        assert not report.summary.conformant

    def test_warnings_alone_are_still_conformant(self, rulepack: Rulepack) -> None:
        """Conformant means nothing blocking, not nothing to look at."""
        report = build_report(
            target="t",
            rulepack=rulepack,
            findings=[_finding(result=Result.WARN)],
            timestamp=_TIMESTAMP,
        )
        assert report.summary.conformant

    def test_timestamp_is_injectable(self, report: Report) -> None:
        """Determinism tests need it pinned; evidence needs it present."""
        assert report.run.timestamp == _TIMESTAMP


class TestCanonicalisation:
    def test_key_order_does_not_change_the_signed_bytes(self, report: Report) -> None:
        """A reformatting tool must not invalidate a valid report."""
        reordered = report_from_dict(
            json.loads(
                json.dumps(report.model_dump(mode="json", exclude_none=True), sort_keys=False)
            )
        )
        assert canonicalise(report) == canonicalise(reordered)

    def test_signature_is_excluded_from_its_own_payload(
        self, report: Report, keys: tuple[Path, Path]
    ) -> None:
        """Otherwise the signature would have to cover itself."""
        signed = sign_report(report, load_private_key(str(keys[0])))
        assert canonicalise(signed) == canonicalise(report)

    def test_canonical_form_is_stable_across_calls(self, report: Report) -> None:
        assert canonicalise(report) == canonicalise(report)


class TestSigning:
    def test_roundtrip_verifies(self, report: Report, keys: tuple[Path, Path]) -> None:
        signed = sign_report(report, load_private_key(str(keys[0])))
        valid, message = verify_report(signed, load_public_key(str(keys[1])))
        assert valid, message

    def test_one_byte_change_breaks_the_signature(
        self, report: Report, keys: tuple[Path, Path]
    ) -> None:
        """The whole point of signing."""
        signed = sign_report(report, load_private_key(str(keys[0])))
        data = json.loads(signed.model_dump_json(exclude_none=True))
        data["findings"][0]["message"] = data["findings"][0]["message"].replace("no", "nO", 1)
        valid, message = verify_report(report_from_dict(data), load_public_key(str(keys[1])))
        assert not valid
        assert "altered after signing" in message

    def test_a_different_key_is_rejected_by_name(
        self, report: Report, keys: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """Verifying against the wrong key must say so, not just fail."""
        other_public = generate_keypair(tmp_path / "other")[1]
        signed = sign_report(report, load_private_key(str(keys[0])))
        valid, message = verify_report(signed, load_public_key(str(other_public)))
        assert not valid
        assert "signed by someone else" in message

    def test_verifying_without_a_key_says_what_it_proves(
        self, report: Report, keys: tuple[Path, Path]
    ) -> None:
        """Integrity is not identity, and the message must not blur that."""
        signed = sign_report(report, load_private_key(str(keys[0])))
        valid, message = verify_report(signed)
        assert valid
        assert "not who produced it" in message

    def test_unsigned_report_is_not_silently_valid(self, report: Report) -> None:
        valid, message = verify_report(report)
        assert not valid
        assert "no signature" in message

    def test_double_signing_is_refused(self, report: Report, keys: tuple[Path, Path]) -> None:
        signed = sign_report(report, load_private_key(str(keys[0])))
        with pytest.raises(SigningError, match="already carries a signature"):
            sign_report(signed, load_private_key(str(keys[0])))


class TestKeyHandling:
    def test_private_key_is_written_owner_only(self, keys: tuple[Path, Path]) -> None:
        mode = keys[0].stat().st_mode
        assert not mode & (stat.S_IRGRP | stat.S_IROTH), (
            "signing key must not be readable by others"
        )

    def test_a_world_readable_key_is_refused(self, keys: tuple[Path, Path]) -> None:
        """A leaked signing key is worse than no signature: it looks trustworthy."""
        keys[0].chmod(0o644)
        with pytest.raises(SigningError, match="readable by group or others"):
            load_private_key(str(keys[0]))

    def test_pem_contents_work_as_well_as_a_path(self, keys: tuple[Path, Path]) -> None:
        """CI secrets hold the PEM itself, not a file."""
        assert load_private_key(keys[0].read_text(encoding="utf-8")) is not None

    def test_missing_key_names_the_path(self, tmp_path: Path) -> None:
        with pytest.raises(SigningError, match="not found"):
            load_private_key(str(tmp_path / "absent.pem"))

    def test_a_non_ed25519_key_is_rejected(self, tmp_path: Path) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        pem = (
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            .private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            .decode()
        )
        with pytest.raises(SigningError, match="Ed25519"):
            load_private_key(pem)


class TestSummary:
    def test_failures_come_first(self, rulepack: Rulepack) -> None:
        """Someone opening a red pipeline should not scroll past green rows."""
        findings = [_finding("MPF-D-001", Result.PASS), _finding("MPF-D-002", Result.FAIL)]
        report = build_report(
            target="t", rulepack=rulepack, findings=findings, timestamp=_TIMESTAMP
        )
        body = render_summary(report)
        assert body.index("MPF-D-002") < body.index("MPF-D-001")

    def test_citation_travels_with_every_failure(self, report: Report) -> None:
        body = render_summary(report)
        assert "Art. 50(1)" in body
        assert "Guidelines §3.2" in body

    def test_unsigned_reports_say_so(self, report: Report) -> None:
        assert "Unsigned report" in render_summary(report)

    def test_signed_reports_name_the_verification_command(
        self, report: Report, keys: tuple[Path, Path]
    ) -> None:
        signed = sign_report(report, load_private_key(str(keys[0])))
        assert "markproof verify-report" in render_summary(signed)

    def test_pipes_in_messages_do_not_break_the_table(self, rulepack: Rulepack) -> None:
        finding = _finding().model_copy(update={"message": "a | b | c"})
        report = build_report(
            target="t", rulepack=rulepack, findings=[finding], timestamp=_TIMESTAMP
        )
        table_row = next(
            line
            for line in render_summary(report).splitlines()
            if "MPF-D-001" in line and "|" in line
        )
        # Count only unescaped pipes: those are the ones Markdown reads as
        # column separators. Four columns need five of them.
        separators = table_row.replace("\\|", "").count("|")
        assert separators == 5, f"escaped pipes must not add columns: {table_row}"

    def test_disclaimer_is_always_present(self, report: Report) -> None:
        assert "not legal advice" in render_summary(report)


class TestTheMarkingLimbIsQualified:
    """Issue #19: a passing marking rule is a smaller statement than it looks.

    Article 50(2) asks for output to be marked **and** detectable as artificially
    generated, and the Guidelines are explicit that satisfying one limb does not
    discharge the other. markproof measures the first against the operator's own
    configuration. It cannot measure the second — whether a third party without
    those keys can detect the mark is a property of the ecosystem, not of the
    endpoint, and no probe run against a system can establish it.

    That gap is live rather than theoretical: text-watermark detection tooling is
    largely announced rather than shipped, and where it exists it is key-gated. So
    the qualification belongs next to the verdict, not in a README the reader of a
    report will never open.
    """

    @staticmethod
    def _report(result: Result, obligation: Obligation | None) -> Report:
        packaged = Path(__file__).resolve().parent.parent / "src" / "markproof" / "rulepacks"
        finding = Finding(
            rule_id="MPF-T-001",
            title="Generated text carries the operator's declared watermark",
            article="Art. 50(2)",
            obligation=obligation,
            guideline_ref=None,
            probe_id="chat",
            result=result,
            message="watermark detected",
        )
        return build_report(
            target="t",
            rulepack=load_rulepack(packaged / "art50-eu-2026.07.yaml"),
            findings=[finding],
            timestamp="2026-09-01T12:00:00+00:00",
        )

    def test_a_passing_marking_rule_carries_the_qualification(self) -> None:
        summary = render_summary(self._report(Result.PASS, Obligation.SYNTHETIC_TEXT_MARKING))
        assert "two limbs" in summary
        assert "not, on its own, Article 50(2) compliance" in summary

    def test_media_marking_too(self) -> None:
        summary = render_summary(self._report(Result.PASS, Obligation.SYNTHETIC_MEDIA_MARKING))
        assert "two limbs" in summary

    def test_a_failing_marking_rule_does_not(self) -> None:
        """Nobody over-reads a failure, and a note on every run is one people skip."""
        summary = render_summary(self._report(Result.FAIL, Obligation.SYNTHETIC_TEXT_MARKING))
        assert "two limbs" not in summary

    def test_a_disclosure_rule_does_not(self) -> None:
        """Article 50(1) has one limb; qualifying it would be noise."""
        summary = render_summary(self._report(Result.PASS, Obligation.AI_INTERACTION))
        assert "two limbs" not in summary

    def test_the_pdf_says_the_same_thing(self) -> None:
        """The PDF is what gets handed to an auditor, so it is where over-reading happens."""
        from markproof.report.pdf_reportlab import report_view

        view = report_view(
            self._report(Result.PASS, Obligation.SYNTHETIC_TEXT_MARKING).model_dump(
                mode="json", exclude_none=True
            )
        )
        assert view.marking_passed

        clean = report_view(
            self._report(Result.PASS, Obligation.AI_INTERACTION).model_dump(
                mode="json", exclude_none=True
            )
        )
        assert not clean.marking_passed

    def test_both_renderers_state_the_same_limit(self) -> None:
        """A reader comparing the two artefacts must find no difference to interpret."""
        from markproof.report import pdf_reportlab, summary

        stripped = summary.MARKING_LIMB_NOTE.replace("**Article 50(2) has two limbs.** ", "")
        assert stripped == pdf_reportlab.MARKING_LIMB_NOTE


class TestKeygenPermissionsSurviveAnExistingFile:
    """`os.open`'s mode argument applies only on creation.

    A key file left by an earlier run under a wider umask, or a placeholder
    somebody touched, keeps its permissions through `O_TRUNC` — and the CLI then
    prints "(mode 600)" over a private key anyone on the machine can read. A claim
    printed next to a fact that contradicts it is the exact defect class this
    project exists to find in other people's systems.
    """

    def test_a_pre_existing_world_readable_file_is_tightened(self, tmp_path: Path) -> None:
        from markproof.report.sign import generate_keypair

        target = tmp_path / "markproof-signing-key.pem"
        target.write_text("placeholder", encoding="utf-8")
        target.chmod(0o644)

        private_path, _ = generate_keypair(tmp_path)
        mode = private_path.stat().st_mode
        assert not mode & (stat.S_IRWXG | stat.S_IRWXO), oct(mode & 0o777)

    def test_a_fresh_file_is_owner_only(self, tmp_path: Path) -> None:
        from markproof.report.sign import generate_keypair

        private_path, _ = generate_keypair(tmp_path)
        assert not private_path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO)
