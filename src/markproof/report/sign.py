# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Canonicalisation and Ed25519 signing of the report.

The chain is short on purpose: serialise the report without its signature block,
canonicalise those bytes with RFC 8785 (JCS), sign them with Ed25519, and put
the signature back. Verification walks the same path and compares.

Canonicalisation is the part that makes this worth anything. Two JSON documents
carrying the same data can differ in key order, whitespace and number
formatting; signing the raw serialisation would mean a reformatting tool
invalidates a valid report, and a verifier that re-serialises differently
rejects it. JCS removes that ambiguity, which is why the exact library version
travels inside the signature block.

The private key never enters the report and is never logged. The public key
does travel with it: it proves the document was not altered after signing.
Whether that key belongs to someone you trust is a separate question, and the
report does not pretend to answer it.
"""

from __future__ import annotations

import base64
import os
import stat
from pathlib import Path
from typing import Any

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from markproof.report.model import Report, Signature

__all__ = [
    "SigningError",
    "canonicalise",
    "generate_keypair",
    "load_private_key",
    "load_public_key",
    "sign_report",
    "verify_report",
]

#: Recorded inside every signature so a later verifier knows which bytes were
#: signed. Pinned in pyproject for the same reason.
_CANONICALIZER = "rfc8785==0.1.4"


class SigningError(RuntimeError):
    """Signing or verification could not be performed as asked."""


def canonicalise(report: Report) -> bytes:
    """The exact bytes a signature covers: the report without its signature."""
    try:
        return rfc8785.dumps(report.to_canonical_dict())
    except rfc8785.CanonicalizationError as exc:  # pragma: no cover - defensive
        raise SigningError(f"report cannot be canonicalised: {exc}") from exc


def generate_keypair(out_dir: Path) -> tuple[Path, Path]:
    """Write a fresh Ed25519 key pair.

    The private key is written with owner-only permissions before any bytes
    reach it, so it is never briefly world-readable on a shared machine.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / "markproof-signing-key.pem"
    public_path = out_dir / "markproof-public-key.pem"

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    # The mode argument to os.open applies only when the file is *created*. A
    # pre-existing key file — a previous run under a wider umask, a placeholder
    # somebody touched — keeps its permissions through O_TRUNC, and the CLI then
    # prints "(mode 600)" over a key anyone on the machine can read. fchmod on the
    # open descriptor fixes that without a window in which the path could be
    # swapped.
    os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as handle:
        handle.write(private_pem)
    public_path.write_bytes(public_pem)
    return private_path, public_path


def load_private_key(source: str) -> Ed25519PrivateKey:
    """Load a private key from a PEM string or a file path.

    Accepting both is what makes the CI story work: a GitHub secret holds the
    PEM directly, while a developer has a file. A file that others can read is
    refused — a signing key that leaked is worse than an unsigned report,
    because it looks trustworthy.
    """
    text = source
    path = Path(source)
    if "BEGIN" not in source:
        if not path.is_file():
            raise SigningError(f"signing key not found: {source}")
        mode = path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            raise SigningError(
                f"{path} is readable by group or others — refusing to use it. "
                f"Fix with: chmod 600 {path}"
            )
        text = path.read_text(encoding="utf-8")

    try:
        key = serialization.load_pem_private_key(text.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise SigningError(f"not a usable PEM private key: {exc}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError(
            f"expected an Ed25519 key, got {type(key).__name__} — reports are "
            "signed with Ed25519 only"
        )
    return key


def load_public_key(source: str) -> Ed25519PublicKey:
    """Load a public key from a PEM string or a file path."""
    text = source
    if "BEGIN" not in source:
        path = Path(source)
        if not path.is_file():
            raise SigningError(f"public key not found: {source}")
        text = path.read_text(encoding="utf-8")

    try:
        key = serialization.load_pem_public_key(text.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SigningError(f"not a usable PEM public key: {exc}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise SigningError(f"expected an Ed25519 public key, got {type(key).__name__}")
    return key


def sign_report(report: Report, private_key: Ed25519PrivateKey) -> Report:
    """Return the report with a signature block attached."""
    if report.signature is not None:
        raise SigningError(
            "report already carries a signature — re-signing would cover "
            "different bytes and silently invalidate the first one"
        )

    payload = canonicalise(report)
    raw_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return report.model_copy(
        update={
            "signature": Signature(
                canonicalizer=_CANONICALIZER,
                public_key=base64.b64encode(raw_public).decode("ascii"),
                value=base64.b64encode(private_key.sign(payload)).decode("ascii"),
            )
        }
    )


def verify_report(report: Report, public_key: Ed25519PublicKey | None = None) -> tuple[bool, str]:
    """Check a report's signature.

    Args:
        report: The report as loaded from disk.
        public_key: The key to verify against. Without one the embedded key is
            used, which proves the document is internally consistent but not
            who signed it — the returned message says so rather than letting a
            reader assume more.

    Returns:
        Whether the signature holds, and a sentence explaining the result.
    """
    if report.signature is None:
        return False, "report carries no signature"

    signature_block = report.signature
    if signature_block.algorithm != "Ed25519":
        return False, f"unsupported signature algorithm: {signature_block.algorithm}"
    if signature_block.canonicalizer != _CANONICALIZER:
        return False, (
            f"report was canonicalised with {signature_block.canonicalizer}, "
            f"this build uses {_CANONICALIZER} — the signed bytes cannot be reproduced"
        )

    try:
        embedded = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(signature_block.public_key, validate=True)
        )
        signature_bytes = base64.b64decode(signature_block.value, validate=True)
    except (ValueError, TypeError) as exc:
        return False, f"signature block is malformed: {exc}"

    key = public_key or embedded
    external = public_key is not None

    if external:
        supplied = key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        carried = embedded.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        if supplied != carried:
            return False, (
                "the supplied public key is not the one embedded in the report — "
                "this report was signed by someone else"
            )

    payload = canonicalise(report)
    try:
        key.verify(signature_bytes, payload)
    except InvalidSignature:
        return False, (
            "signature does not match the report contents — the document was altered after signing"
        )

    if external:
        return True, "signature valid against the supplied public key"
    return True, (
        "signature valid against the key embedded in the report — this proves the "
        "document is unaltered, not who produced it. Supply --key to check the signer."
    )


def report_from_dict(data: dict[str, Any]) -> Report:
    """Load a report from parsed JSON, with a readable error on mismatch."""
    try:
        return Report.model_validate(data)
    except Exception as exc:
        raise SigningError(f"not a valid markproof report: {exc}") from exc
