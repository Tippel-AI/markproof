# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""The rule evaluator: ``evaluate(rulepack, evidence) -> findings``.

A pure function. No I/O, no clock, no network, no LLM. Identical inputs must
produce byte-identical findings, which is what makes the signed report worth
signing — the determinism test runs each golden evidence file through the full
pipeline twice (signature and timestamp zeroed) and asserts byte equality.

Result values: PASS / FAIL / WARN / SKIP. Stable ordering; every FAIL references
at least one artefact hash; an unknown ``check.type`` is a hard config error
rather than a silent SKIP.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from markproof.checks.c2pa_verify import C2paOutcome, C2paResult, verify_media
from markproof.checks.disclosure import (
    DisclosureOutcome,
    DisclosureResult,
    PatternSet,
    check_disclosure,
)
from markproof.checks.labels import (
    LabelOutcome,
    LabelPatternSet,
    LabelResult,
    check_labels,
)
from markproof.checks.synthid import (
    SynthIdOutcome,
    SynthIdResult,
    WatermarkConfig,
    detect_watermark,
)
from markproof.probes.base import Evidence
from markproof.rules.schema import (
    Applicability,
    C2paVerifyCheck,
    DisclosurePatternCheck,
    LabelPresenceCheck,
    Obligation,
    ProbeKind,
    Rule,
    Rulepack,
    Severity,
    SynthIdDetectCheck,
)

__all__ = [
    "OPERATIONAL_RULE_ID",
    "ConfigurationRequiredError",
    "Finding",
    "Result",
    "UnsupportedCheckError",
    "combine",
    "evaluate",
    "exit_code_for",
    "probe_failure_finding",
]


class UnsupportedCheckError(RuntimeError):
    """A rulepack asked for a check this build cannot perform.

    Deliberately fatal. Silently skipping an unknown check would let a rulepack
    claim coverage the tool never delivered — the failure mode a compliance
    tool must not have.
    """


class ConfigurationRequiredError(RuntimeError):
    """A rule needs configuration the run did not supply.

    Fatal rather than skipped: a rulepack that asks for text marking and gets
    silence would otherwise report a clean run over a check that never happened.
    """


class Result(StrEnum):
    """The verdict for one rule against one probe."""

    PASS = "PASS"  # noqa: S105 - a verdict, not a credential
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class Finding(BaseModel):
    """One rule's verdict, with the evidence that produced it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    title: str
    article: str
    obligation: Obligation | None = None
    """Which Article 50 duty this finding is about.

    ``None`` for operational findings: ``MPF-X-001`` reports that a probe could
    not run, which is a fact about the run and not about an obligation. Giving
    it one would put it in scope for a declaration that has nothing to say
    about it.
    """

    guideline_ref: str | None = None
    """Clause or margin number behind the rule, where there is one.

    The default is what makes a report re-readable. Reports are written with
    ``exclude_none=True``, so a null here vanishes from the JSON — and without a
    default, loading that file back fails with "field required". The findings that
    carry no guideline reference are exactly the operational ones (``MPF-X-001``,
    an endpoint that could not be reached), so before this default a report about
    an unreachable endpoint could not be verified: the case where the audit trail
    matters most was the one that could not be checked.
    """

    probe_id: str
    result: Result
    message: str
    detail: dict[str, str | int | list[str]] = Field(default_factory=dict)
    evidence_sha256: tuple[str, ...] = ()

    @property
    def is_blocking(self) -> bool:
        return self.result is Result.FAIL


#: How a failed check maps onto a result, given the rule's severity.
_SEVERITY_TO_RESULT = {
    Severity.FAIL: Result.FAIL,
    Severity.WARN: Result.WARN,
}

#: Outcomes that are not a clean pass but not a confident failure either. They
#: always become WARN, regardless of severity: the tool saw something a human
#: needs to look at, and inventing a verdict would be the guess we refuse to make.
_INCONCLUSIVE = {DisclosureOutcome.NEAR_MISS, DisclosureOutcome.NO_EVIDENCE}

#: C2PA outcomes that describe a problem with the evidence rather than with the
#: asset. An unreadable download says nothing about compliance, so it warns.
_C2PA_INCONCLUSIVE = {C2paOutcome.UNREADABLE}


#: Rule id for operational findings — a probe that could not be performed.
#: Reserved here rather than in a rulepack: it describes the run, not an
#: obligation, and it must exist even when the rulepack is silent about it.
OPERATIONAL_RULE_ID = "MPF-X-001"


def probe_failure_finding(probe_id: str, reason: str) -> Finding:
    """A probe that could not be performed at all.

    This is a FAIL, not a skip. "The endpoint was unreachable" and "the endpoint
    is compliant" must never look alike in a report: a pipeline that goes green
    because nothing could be checked is the worst outcome this tool has.

    It is also why the run still writes a report — evidence that the check was
    attempted and why it did not produce a verdict is more useful than no file
    at all.
    """
    return Finding(
        rule_id=OPERATIONAL_RULE_ID,
        title="Probe could not be performed",
        article="—",
        guideline_ref=None,
        probe_id=probe_id,
        result=Result.FAIL,
        message=reason,
        detail={"outcome": "probe_error"},
    )


def combine(evaluated: list[Finding], probe_failures: list[Finding]) -> list[Finding]:
    """Merge rule findings with operational ones into the report's final order.

    Exists so that exactly one definition of "the order findings appear in" is
    shipped. The CLI used to sort inline, which meant the determinism gate could
    only ever test a copy of that logic — and a copy that drifted would let the
    gate pass while real reports changed shape. Both call this now.

    The key is total: rule ids are unique within a pack and probe ids are unique
    within a config, so no two findings tie and the result never depends on the
    order probes happened to finish in.
    """
    return sorted(evaluated + probe_failures, key=lambda f: (f.rule_id, f.probe_id))


def evaluate(
    rulepack: Rulepack,
    evidences: list[Evidence],
    pattern_sets: dict[str, PatternSet],
    watermark_config: WatermarkConfig | None = None,
    label_sets: dict[str, LabelPatternSet] | None = None,
    applicability: Applicability | None = None,
) -> list[Finding]:
    """Evaluate every applicable rule against every probe's evidence.

    Pattern sets are passed in already loaded, which keeps this function free of
    I/O and makes it trivially testable.

    Args:
        rulepack: The validated rulepack.
        evidences: One entry per probe that ran.
        pattern_sets: Loaded pattern files, keyed by ``patterns_file`` name.
        applicability: The target's declaration of which Article 50 obligations
            bind it. ``None`` — and any obligation it does not mention — leaves
            the rule running, so silence never removes a check.

    Returns:
        Findings sorted by (rule id, probe id) — a stable order that does not
        depend on dict iteration or on the order probes happened to finish.

    Raises:
        UnsupportedCheckError: if a rule requests an unimplemented check type.
        KeyError: if a rule references a pattern file that was not supplied.
    """
    findings: list[Finding] = []

    declaration = applicability if applicability is not None else Applicability()

    for evidence in evidences:
        for rule in rulepack.rules_for(evidence.probe_kind):
            if not declaration.applies(rule.obligation):
                findings.append(_out_of_scope_finding(rule, evidence))
                continue
            findings.append(
                _evaluate_rule(
                    rule, evidence, pattern_sets, watermark_config, label_sets, declaration
                )
            )

    findings.sort(key=lambda f: (f.rule_id, f.probe_id))
    return findings


def _out_of_scope_finding(rule: Rule, evidence: Evidence) -> Finding:
    """A rule the target declared does not bind it.

    Visible, attributed and counted — never dropped. The point of the
    declaration is that a reader can see what a green run left out and on whose
    word, so a silently shorter findings list would defeat it. The message names
    the obligation and says plainly that this is the operator's claim, not a
    measurement.
    """
    return Finding(
        rule_id=rule.id,
        title=rule.title,
        article=rule.article,
        obligation=rule.obligation,
        guideline_ref=rule.guideline_ref,
        probe_id=evidence.probe_id,
        result=Result.SKIP,
        message=(
            f"not applicable — the target declares no {rule.obligation.value} "
            f"obligation ({rule.article})"
        ),
        detail={"outcome": "not_applicable", "declared_by": "target configuration"},
    )


def _unverified_finding(
    rule: Rule,
    evidence: Evidence,
    applicability: Applicability,
    *,
    missing: str,
    remedy: str,
    hashes: tuple[str, ...] = (),
) -> Finding:
    """A check that declined because the run lacked what it needed to look.

    The same absence means two different things, and the declaration is what
    tells them apart. An operator who never claimed the obligation gets a SKIP:
    nothing was promised and nothing is owed. One who declared it applicable
    gets a WARN, because "we mark our text", "nothing was checked" and a green
    build is the silent pass this project exists to remove.

    Not a FAIL either way. markproof does not know that no marking exists — it
    knows it was not given the means to look, and a provider marking
    server-side is a real answer this tool cannot see. Failing on that would be
    the guess we refuse everywhere else.
    """
    declared = applicability.is_declared_applicable(rule.obligation)
    if declared:
        result = Result.WARN
        message = (
            f"the target declares a {rule.obligation.value} obligation, but {missing} — "
            f"it was not verified. {remedy}"
        )
    else:
        result = Result.SKIP
        message = f"{missing}. {remedy}"

    return Finding(
        rule_id=rule.id,
        title=rule.title,
        article=rule.article,
        obligation=rule.obligation,
        guideline_ref=rule.guideline_ref,
        probe_id=evidence.probe_id,
        result=result,
        message=message,
        detail={
            "outcome": "unverified",
            "declared_applicable": "yes" if declared else "not declared",
        },
        evidence_sha256=hashes,
    )


def _evaluate_rule(
    rule: Rule,
    evidence: Evidence,
    pattern_sets: dict[str, PatternSet],
    watermark_config: WatermarkConfig | None = None,
    label_sets: dict[str, LabelPatternSet] | None = None,
    applicability: Applicability | None = None,
) -> Finding:
    """Apply one rule to one probe's evidence."""
    check = rule.check

    if isinstance(check, DisclosurePatternCheck):
        pattern_set = pattern_sets.get(check.patterns_file)
        if pattern_set is None:
            raise KeyError(
                f"rule {rule.id} references pattern file {check.patterns_file!r}, "
                "which was not loaded"
            )
        return _finding_from_disclosure(
            rule, evidence, check_disclosure(evidence, check, pattern_set)
        )

    if isinstance(check, C2paVerifyCheck):
        return _finding_from_c2pa(rule, evidence, check)

    if isinstance(check, LabelPresenceCheck):
        label_set = (label_sets or {}).get(check.labels_file)
        if label_set is None:
            raise KeyError(
                f"rule {rule.id} references label file {check.labels_file!r}, which was not loaded"
            )
        return _finding_from_labels(rule, evidence, check_labels(evidence, check, label_set))

    if isinstance(check, SynthIdDetectCheck):
        declaration = applicability if applicability is not None else Applicability()
        if watermark_config is None:
            # Visible, not silent, and not a hard stop: a rulepack is taken as a
            # whole, and an operator who does not watermark text still needs the
            # disclosure and media rules to run.
            return _unverified_finding(
                rule,
                evidence,
                declaration,
                missing="no watermark configuration was supplied",
                remedy=(
                    "Set text_marking.watermark_config in markproof.yaml to verify text marking."
                ),
            )
        return _finding_from_synthid(rule, evidence, check, watermark_config, declaration)

    raise UnsupportedCheckError(
        f"rule {rule.id} requests check type {getattr(check, 'type', type(check).__name__)!r}, "
        "which this build does not implement"
    )


def _finding_from_c2pa(rule: Rule, evidence: Evidence, check: C2paVerifyCheck) -> Finding:
    """Verify every artefact the probe collected and fold the results into one finding.

    An asset that fails drags the whole finding down: shipping ten images of
    which one lost its manifest is not nine-tenths compliant, it is a delivery
    regression that reaches some users.
    """
    artifacts = [a for turn in evidence.turns for a in turn.artifacts]
    if not artifacts:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.WARN,
            message="no media collected — nothing could be checked",
            detail={"outcome": "no_media"},
        )

    results: list[C2paResult] = []
    for artifact in artifacts:
        if artifact.data is None:
            results.append(
                C2paResult(
                    outcome=C2paOutcome.UNREADABLE,
                    artifact_id=artifact.id,
                    detail="artefact bytes are not available in this evidence",
                )
            )
            continue
        results.append(
            verify_media(
                artifact.data,
                artifact.media_type,
                check,
                artifact_id=artifact.id,
            )
        )

    failed = [r for r in results if not r.passed]
    detail: dict[str, str | int | list[str]] = {
        "checked": len(results),
        "outcome": "verified" if not failed else failed[0].outcome.value,
        "assets": sorted(r.artifact_id for r in results),
    }
    if failed:
        detail["failed_assets"] = sorted(r.artifact_id for r in failed)
        types = sorted({r.source_type for r in failed if r.source_type})
        if types:
            detail["declared_source_types"] = types

    hashes = tuple(a.sha256 for turn in evidence.turns for a in turn.artifacts)

    if not failed:
        noun = "asset" if len(results) == 1 else "assets"
        verb = "carries" if len(results) == 1 else "carry"
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.PASS,
            message=f"{len(results)} {noun} {verb} a valid, correctly marked manifest",
            detail=detail,
            evidence_sha256=hashes,
        )

    first = failed[0]
    inconclusive = all(r.outcome in _C2PA_INCONCLUSIVE for r in failed)
    return Finding(
        rule_id=rule.id,
        title=rule.title,
        article=rule.article,
        obligation=rule.obligation,
        guideline_ref=rule.guideline_ref,
        probe_id=evidence.probe_id,
        result=Result.WARN if inconclusive else _SEVERITY_TO_RESULT[rule.severity],
        message=(
            f"{len(failed)} of {len(results)} asset(s) failed: "
            f"{first.detail or first.outcome.value}"
        ),
        detail=detail,
        evidence_sha256=hashes,
    )


def _finding_from_disclosure(rule: Rule, evidence: Evidence, outcome: DisclosureResult) -> Finding:
    """Turn a disclosure outcome into a finding."""
    hashes = tuple(
        t.response_sha256 for t in evidence.turns if t.prompt_id in outcome.inspected_prompt_ids
    )
    detail: dict[str, str | int | list[str]] = {
        "outcome": outcome.outcome.value,
        "lang": outcome.lang,
        "inspected_prompts": list(outcome.inspected_prompt_ids),
        "matched_patterns": sorted({h.pattern_id for h in outcome.hits if h.kind == "positive"}),
    }
    near_misses = sorted({h.pattern_id for h in outcome.hits if h.kind == "negative"})
    if near_misses:
        detail["near_miss_patterns"] = near_misses

    if outcome.outcome is DisclosureOutcome.DISCLOSED:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.PASS,
            message=_pass_message(outcome),
            detail=detail,
            evidence_sha256=hashes,
        )

    if outcome.outcome in _INCONCLUSIVE:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.WARN,
            message=_inconclusive_message(outcome),
            detail=detail,
            evidence_sha256=hashes,
        )

    return Finding(
        rule_id=rule.id,
        title=rule.title,
        article=rule.article,
        obligation=rule.obligation,
        guideline_ref=rule.guideline_ref,
        probe_id=evidence.probe_id,
        result=_SEVERITY_TO_RESULT[rule.severity],
        message=_failure_message(outcome),
        detail=detail,
        evidence_sha256=hashes,
    )


def _finding_from_labels(rule: Rule, evidence: Evidence, outcome: LabelResult) -> Finding:
    """Turn a label outcome into a finding.

    Presence is decidable; prominence is not. v0.1 reports only whether the
    wording is there at all, which is why the shipped rule warns rather than
    fails — telling an operator their label is missing is useful, telling them
    it is badly placed would be a design opinion dressed as a verdict.
    """
    matched = sorted({h.pattern_id for h in outcome.hits if h.kind == "positive"})
    near_misses = sorted({h.pattern_id for h in outcome.hits if h.kind == "negative"})

    detail: dict[str, str | int | list[str]] = {
        "outcome": outcome.outcome.value,
        "category": outcome.category,
        "lang": outcome.lang,
    }
    if matched:
        detail["matched_labels"] = matched
    if near_misses:
        detail["near_miss_labels"] = near_misses
    if outcome.unlabelled_prompt_ids:
        detail["unlabelled"] = list(outcome.unlabelled_prompt_ids)

    hashes = tuple(
        t.response_sha256 for t in evidence.turns if t.prompt_id in outcome.inspected_prompt_ids
    )

    if outcome.outcome is LabelOutcome.LABELLED:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.PASS,
            message=f"label present ({', '.join(matched)})",
            detail=detail,
            evidence_sha256=hashes,
        )

    if outcome.outcome is LabelOutcome.NO_PERCEIVABLE_TEXT:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.SKIP,
            message=(
                "no perceivable text to inspect for a label — a media endpoint "
                "returns an API payload, not the page where the content is shown. "
                "Point a 'ui' probe at that page to check this obligation."
                if evidence.probe_kind is ProbeKind.MEDIA
                else "no perceivable text to inspect for a label"
            ),
            detail=detail,
            evidence_sha256=hashes,
        )

    if outcome.outcome is LabelOutcome.AMBIGUOUS:
        # Wording that resembles a label is a judgement call, and inventing a
        # verdict there is the guessing this tool refuses to do.
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.WARN,
            message=(
                "wording resembles a label but does not state artificial origin "
                f"({', '.join(near_misses)}) — needs human review"
            ),
            detail=detail,
            evidence_sha256=hashes,
        )

    return Finding(
        rule_id=rule.id,
        title=rule.title,
        article=rule.article,
        obligation=rule.obligation,
        guideline_ref=rule.guideline_ref,
        probe_id=evidence.probe_id,
        result=_SEVERITY_TO_RESULT[rule.severity],
        message=f"no {outcome.category} label found in the perceivable text",
        detail=detail,
        evidence_sha256=hashes,
    )


def _finding_from_synthid(
    rule: Rule,
    evidence: Evidence,
    check: SynthIdDetectCheck,
    config: WatermarkConfig,
    applicability: Applicability,
) -> Finding:
    """Verify text marking on the text this rule covers.

    Which text that is depends on the surface. A chat endpoint returns nothing
    but generated text, so the response *is* the sample. A rendered page is
    mostly not generated — navigation, headings, footer, cookie banner — and a
    mean-g score over that mixture is a weighted average of marked and unmarked
    text. The fixture sweep put partly-marked text at 0.586-0.657 against a
    ``watermarked_at`` of 0.70, so scoring a whole document would land a
    correctly marked page in the uncertain band and, by default, fail it. So on
    a rendered page this scores the region the operator named, and nothing else.
    """
    if evidence.probe_kind is ProbeKind.UI:
        scope = evidence.content_scope
        if scope is None:
            return _unverified_finding(
                rule,
                evidence,
                applicability,
                missing="the probe recorded no generated-text region",
                remedy=(
                    "Set content_selector on the UI probe to name the element holding "
                    "generated text. Scoring a whole page averages template text with "
                    "generated text and yields a number that means nothing."
                ),
            )
        sample, sample_sha256 = scope.text, scope.sha256
        source: dict[str, str | int | list[str]] = {"content_selector": scope.selector}
    else:
        turns = list(evidence.turns)
        if not turns:
            return Finding(
                rule_id=rule.id,
                title=rule.title,
                article=rule.article,
                obligation=rule.obligation,
                guideline_ref=rule.guideline_ref,
                probe_id=evidence.probe_id,
                result=Result.WARN,
                message="no response to inspect for text marking",
                detail={"outcome": "no_evidence"},
            )
        # The longest response gives the detector the most to work with; a short
        # one would be skipped anyway, and reporting the strongest available
        # sample is the fairest reading of the endpoint's behaviour.
        turn = max(turns, key=lambda t: len(t.response.content))
        sample, sample_sha256 = turn.response.content, turn.response_sha256
        source = {"prompt_id": turn.prompt_id}

    result: SynthIdResult = detect_watermark(sample, check, config)

    detail: dict[str, str | int | list[str]] = {
        "outcome": result.outcome.value,
        "detector": result.detector,
        "token_count": result.token_count,
        **source,
    }
    if result.score is not None:
        detail["score"] = str(result.score)
    if result.thresholds is not None:
        detail["thresholds"] = [str(result.thresholds[0]), str(result.thresholds[1])]

    hashes = (sample_sha256,)

    if result.outcome is SynthIdOutcome.WATERMARKED:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.PASS,
            message=f"watermark detected (mean g {result.score}, {result.token_count} tokens)",
            detail=detail,
            evidence_sha256=hashes,
        )

    if result.outcome is SynthIdOutcome.TOO_SHORT:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.SKIP,
            message=result.detail or "response too short to score",
            detail=detail,
            evidence_sha256=hashes,
        )

    if result.outcome is SynthIdOutcome.UNSUPPORTED:
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=Result.WARN,
            message=result.detail or "detector not available in this build",
            detail=detail,
            evidence_sha256=hashes,
        )

    if result.outcome is SynthIdOutcome.UNCERTAIN:
        # The rule decides what an inconclusive score means; the default is to
        # fail, because an operator claiming to watermark should clear the bar.
        if check.on_uncertain == "skip":
            outcome_result = Result.SKIP
        else:
            outcome_result = _SEVERITY_TO_RESULT[Severity(check.on_uncertain)]
        return Finding(
            rule_id=rule.id,
            title=rule.title,
            article=rule.article,
            obligation=rule.obligation,
            guideline_ref=rule.guideline_ref,
            probe_id=evidence.probe_id,
            result=outcome_result,
            message=result.detail or "watermark score inconclusive",
            detail=detail,
            evidence_sha256=hashes,
        )

    return Finding(
        rule_id=rule.id,
        title=rule.title,
        article=rule.article,
        obligation=rule.obligation,
        guideline_ref=rule.guideline_ref,
        probe_id=evidence.probe_id,
        result=_SEVERITY_TO_RESULT[rule.severity],
        message=result.detail or "no watermark detected",
        detail=detail,
        evidence_sha256=hashes,
    )


def _pass_message(outcome: DisclosureResult) -> str:
    # Distinct patterns, in stable order — the same pattern hitting two bound
    # prompts is one piece of evidence, and listing it twice reads like a bug.
    matched = sorted({h.pattern_id for h in outcome.hits if h.kind == "positive"})
    plural = "s" if len(matched) != 1 else ""
    return f"disclosure found ({len(matched)} pattern{plural} matched: {', '.join(matched)})"


def _inconclusive_message(outcome: DisclosureResult) -> str:
    if outcome.outcome is DisclosureOutcome.NO_EVIDENCE:
        return "no response in scope for this rule — nothing could be checked"
    near = [h.pattern_id for h in outcome.hits if h.kind == "negative"]
    return (
        "wording resembles a disclosure but does not state the AI nature "
        f"({', '.join(near)}) — needs human review"
    )


def _failure_message(outcome: DisclosureResult) -> str:
    if outcome.outcome is DisclosureOutcome.LATE:
        return "disclosure appears later in the conversation, not before the first user message"
    return "no AI disclosure found in the responses in scope"


def exit_code_for(findings: list[Finding]) -> int:
    """Process exit code: 1 as soon as one finding blocks, else 0.

    WARN never sets the exit code. A pipeline that goes red on ambiguity trains
    people to ignore it.
    """
    return 1 if any(f.is_blocking for f in findings) else 0
