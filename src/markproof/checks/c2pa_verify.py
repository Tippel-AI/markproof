# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""C2PA manifest verification (Art. 50(2)) — the first half of the unique lane.

Single point of contact with ``c2pa-python`` (official CAI bindings for
c2pa-rs, pinned to ``0.37.*``). Everything the SDK exposes is wrapped here so
that the 0.x API churn touches exactly one module.

Verdict ladder:

1. manifest present?              -> otherwise MANIFEST_MISSING
2. manifest validates (hash bindings intact, signature chain formally valid)?
3. required assertions satisfied, e.g.
   ``c2pa.actions.v2: digitalSourceType == trainedAlgorithmicMedia``?

Step 3 is the one that matters for Article 50 and the one no other tool
performs: a validly signed asset declaring a camera capture is *correctly
signed and not AI-marked*, which is a failure of this obligation, not a pass.

v1 boundary, documented rather than papered over: trust-list evaluation ("is
this signer trustworthy?") is v1.1. v1 accepts self-signed chains when the rule
says ``trust: { allow_self_signed: true }``, and says so in the finding.
"""

from __future__ import annotations

import io
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from markproof.rules.schema import C2paVerifyCheck

__all__ = [
    "AssertionMiss",
    "C2paOutcome",
    "C2paResult",
    "verify_media",
]

#: Assertion label carrying the provenance of a media asset.
_ACTIONS_LABEL_PREFIX = "c2pa.actions"

#: Keys under which a digital source type may appear, across assertion versions.
_SOURCE_TYPE_KEYS = ("digitalSourceType", "digital_source_type")

#: IPTC prefix the spec uses for these values. Rules name the bare term
#: ("trainedAlgorithmicMedia"); assets carry the full URI. Comparing suffixes
#: keeps rulepacks readable without accepting a different vocabulary.
_IPTC_PREFIX = "http://cv.iptc.org/newscodes/digitalsourcetype/"

#: Failure code c2pa-rs reports when no configured anchor vouches for the signer.
_UNTRUSTED_CODE = "signingCredential.untrusted"


class C2paOutcome(StrEnum):
    """What the verification concluded.

    ``UNREADABLE`` is separate from ``MANIFEST_MISSING`` on purpose: a truncated
    download and a stripped manifest look alike in a summary, but one is an
    infrastructure problem and the other is the finding this tool exists for.
    """

    VERIFIED = "verified"
    MANIFEST_MISSING = "manifest_missing"
    INVALID = "invalid"
    WRONG_SOURCE_TYPE = "wrong_source_type"
    MISSING_ASSERTION = "missing_assertion"
    UNTRUSTED_SIGNER = "untrusted_signer"
    REMOTE_MANIFEST = "remote_manifest"
    UNREADABLE = "unreadable"


class AssertionMiss(BaseModel):
    """One required assertion that was absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str


class C2paResult(BaseModel):
    """Outcome plus the evidence behind it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: C2paOutcome
    artifact_id: str
    validation_state: str | None = None
    source_type: str | None = None
    signer: str | None = None
    self_signed: bool | None = None
    missing_assertions: tuple[AssertionMiss, ...] = ()
    failure_codes: tuple[str, ...] = ()
    detail: str | None = None

    @property
    def passed(self) -> bool:
        return self.outcome is C2paOutcome.VERIFIED


def _normalise_source_type(value: str) -> str:
    """Reduce an IPTC source-type URI to its bare term."""
    if value.startswith(_IPTC_PREFIX):
        return value[len(_IPTC_PREFIX) :]
    return value.rsplit("/", 1)[-1] if "/" in value else value


def _find_source_type(manifest: dict[str, Any]) -> str | None:
    """Dig the declared digital source type out of a manifest.

    Looks through the actions assertions, which is where both the v1 and v2
    action schemas put it. Returns the bare term, or None if the asset never
    declares one — which is itself the answer to the Article 50 question.
    """
    for assertion in manifest.get("assertions", []) or []:
        label = str(assertion.get("label", ""))
        if not label.startswith(_ACTIONS_LABEL_PREFIX):
            continue
        data = assertion.get("data") or {}
        for action in data.get("actions", []) or []:
            for key in _SOURCE_TYPE_KEYS:
                raw = action.get(key)
                if isinstance(raw, str) and raw:
                    return _normalise_source_type(raw)
        for key in _SOURCE_TYPE_KEYS:
            raw = data.get(key)
            if isinstance(raw, str) and raw:
                return _normalise_source_type(raw)
    return None


def _assertion_labels(manifest: dict[str, Any]) -> set[str]:
    return {str(a.get("label", "")) for a in manifest.get("assertions", []) or [] if a.get("label")}


def _failure_codes(reader: Any) -> list[str]:
    """Failure codes for the active manifest, in the order the SDK reports them.

    Returns an empty list when the SDK reports nothing — an absent result is not
    evidence of success, so callers must decide on the validation state first.
    """
    try:
        raw = reader.get_validation_results()
    except Exception:  # SDK surface is not fully typed; any failure means "no codes"
        return []
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, dict):
        return []
    active = parsed.get("activeManifest") or {}
    return [str(f.get("code", "")) for f in active.get("failure", []) if f.get("code")]


def _signer_of(manifest: dict[str, Any]) -> tuple[str | None, bool | None]:
    """Issuer common name and whether the chain looks self-signed."""
    info = manifest.get("signature_info") or {}
    issuer = info.get("issuer")
    cert_serial = info.get("cert_serial_number")
    # c2pa-rs reports issuer and, for self-issued certs, the same name as the
    # subject. Absent a subject field we fall back to "unknown", never to a
    # claim of trustworthiness.
    self_signed = None
    if issuer is not None:
        self_signed = issuer == info.get("common_name", issuer) and cert_serial is not None
    return (str(issuer) if issuer else None, self_signed)


def verify_media(
    data: bytes,
    media_type: str,
    check: C2paVerifyCheck,
    *,
    artifact_id: str,
) -> C2paResult:
    """Verify one media payload against a rule's C2PA requirements.

    Pure with respect to the network: the bytes are already in hand, and remote
    manifests are refused rather than fetched, so the same payload always yields
    the same verdict.
    """
    import c2pa

    try:
        reader = c2pa.Reader(media_type, stream=io.BytesIO(data))
    except c2pa.C2paError.ManifestNotFound:
        return C2paResult(
            outcome=C2paOutcome.MANIFEST_MISSING,
            artifact_id=artifact_id,
            detail="no C2PA manifest embedded in the delivered bytes",
        )
    except c2pa.C2paError as exc:
        # Includes truncated payloads and formats the SDK cannot parse. Not the
        # same as "no manifest", and reported as its own outcome.
        return C2paResult(
            outcome=C2paOutcome.UNREADABLE,
            artifact_id=artifact_id,
            detail=f"{type(exc).__name__}: {exc}",
        )

    try:
        return _evaluate_reader(reader, check, artifact_id=artifact_id)
    finally:
        reader.close()


def _evaluate_reader(reader: Any, check: C2paVerifyCheck, *, artifact_id: str) -> C2paResult:
    """Walk the verdict ladder over an open reader."""
    if not check.allow_remote_manifests and reader.get_remote_url():
        return C2paResult(
            outcome=C2paOutcome.REMOTE_MANIFEST,
            artifact_id=artifact_id,
            detail=(
                "manifest is referenced remotely, not embedded — a CDN or a "
                "conversion can drop it before the asset reaches the user"
            ),
        )

    try:
        manifest_store = json.loads(reader.json())
    except (ValueError, TypeError) as exc:
        return C2paResult(
            outcome=C2paOutcome.UNREADABLE,
            artifact_id=artifact_id,
            detail=f"manifest store is not valid JSON: {exc}",
        )

    active_label = manifest_store.get("active_manifest")
    manifest = (manifest_store.get("manifests") or {}).get(active_label) or {}
    signer, self_signed = _signer_of(manifest)

    # NOT reader.is_valid: that property reports whether the reader object is
    # still open (ManagedResource liveness), and returns True for a tampered
    # asset. Validity lives in the validation state.
    state_str = str(reader.get_validation_state() or "")
    failures = _failure_codes(reader)

    if state_str.lower() == "invalid":
        altered = [c for c in failures if "mismatch" in c]
        return C2paResult(
            outcome=C2paOutcome.INVALID,
            artifact_id=artifact_id,
            validation_state=state_str,
            signer=signer,
            self_signed=self_signed,
            failure_codes=tuple(failures),
            detail=(
                "manifest present but validation failed — the asset was altered after signing"
                + (f" ({', '.join(altered)})" if altered else "")
            ),
        )

    # Trust is configuration, not a property of the file: the same asset reads
    # as Trusted or as untrusted depending on which anchors are loaded. An
    # untrusted signer is therefore its own finding, never conflated with a
    # missing or wrong assertion.
    if _UNTRUSTED_CODE in failures and not check.trust.allow_self_signed:
        return C2paResult(
            outcome=C2paOutcome.UNTRUSTED_SIGNER,
            artifact_id=artifact_id,
            validation_state=state_str,
            signer=signer,
            self_signed=self_signed,
            failure_codes=tuple(failures),
            detail=(
                "manifest is intact but its signer is not in the configured trust list — "
                "set trust.allow_self_signed to accept development certificates"
            ),
        )

    missing = tuple(
        AssertionMiss(label=label)
        for label in check.require_assertions
        if label not in _assertion_labels(manifest)
    )
    if missing:
        return C2paResult(
            outcome=C2paOutcome.MISSING_ASSERTION,
            artifact_id=artifact_id,
            validation_state=state_str,
            signer=signer,
            self_signed=self_signed,
            missing_assertions=missing,
            detail=f"required assertion(s) absent: {', '.join(m.label for m in missing)}",
        )

    source_type = _find_source_type(manifest)
    if check.accept_source_types is not None:
        accepted = {_normalise_source_type(s) for s in check.accept_source_types}
        if source_type not in accepted:
            wanted = " or ".join(sorted(accepted))
            return C2paResult(
                outcome=C2paOutcome.WRONG_SOURCE_TYPE,
                artifact_id=artifact_id,
                validation_state=state_str,
                source_type=source_type,
                signer=signer,
                self_signed=self_signed,
                detail=(
                    f"asset is validly signed but declares "
                    f"{source_type or 'no digital source type'}, not {wanted} — "
                    "signed is not the same as marked as AI-generated"
                ),
            )

    return C2paResult(
        outcome=C2paOutcome.VERIFIED,
        artifact_id=artifact_id,
        validation_state=state_str,
        source_type=source_type,
        signer=signer,
        self_signed=self_signed,
    )
