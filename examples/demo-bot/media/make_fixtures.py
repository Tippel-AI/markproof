# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the demo-bot's image fixtures. Development tool, never a runtime.

The demo-bot serves the three PNGs next to this script; it does not sign
anything at request time. Signing per request would mean a fresh ECDSA nonce
and a fresh signing time in every response, so the same request would return
different bytes each time and the determinism gate would be measuring the
random number generator (README §Determinism). The committed files are the
source of truth; this script exists so anyone can see — and redo — how they
were made.

The three fixtures share pixel-for-pixel identical image data. Only the
provenance differs:

``demo-signed.png``     valid C2PA manifest, ``digitalSourceType`` =
                        ``trainedAlgorithmicMedia`` — what Art. 50(2) asks a
                        generator to attach.
``demo-unsigned.png``   the bare image, no manifest at all. The common real
                        failure: a CDN or an image pipeline re-encoded the
                        asset and dropped the C2PA chunk on the way out.
``demo-wrongtype.png``  manifest present and cryptographically valid, but the
                        action claims ``algorithmicMedia`` — algorithmically
                        produced, *not* by a trained model. A check that only
                        asks "is there a manifest?" waves this through, and so
                        does a substring match on "algorithmicMedia". That is
                        the point of the fixture.

Auflage H2 (own production only): every pixel here is computed by the code
below — a diamond-ring pattern and a hand-rolled 5x7 bitmap font. No third
party asset enters the repository, not even as a thumbnail. The C2PA SDK
derives its claim thumbnail from our own image.

The signing identity is an *ephemeral, self-signed development chain*: a new
key pair per run, never written to disk, never committed. That matches the v1
boundary in ``markproof.checks.c2pa_verify`` — trust-list evaluation is v1.1,
so v1 accepts self-signed chains when the rule says so. It also means a rerun
produces different bytes (new key, new signing time, new instance id); the
manifest *content* stays the same, the file hash does not. Update the table in
README.md when you rerun.

Needs the dev environment, not the demo-bot's own requirements.txt:

    pip install "c2pa-python==0.37.*" "cryptography>=43"
    python examples/demo-bot/media/make_fixtures.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import c2pa
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

HERE = Path(__file__).resolve().parent

WIDTH = 512
HEIGHT = 512

#: Indexed PNG: six flat colours compress to a few kB and stay byte-stable
#: across zlib versions far better than a photographic gradient would.
PALETTE = (
    (0x0F, 0x17, 0x20),  # 0 ground
    (0x17, 0x24, 0x31),  # 1 ring
    (0x1F, 0x33, 0x45),  # 2 ring
    (0x2A, 0x45, 0x5C),  # 3 ring
    (0x37, 0x5B, 0x77),  # 4 ring
    (0xF2, 0xF5, 0xF7),  # 5 text and frame
)
GROUND, TEXT = 0, 5

#: IPTC digital source type vocabulary — the controlled values a C2PA action
#: may carry. Art. 50(2) cares about exactly one of them.
IPTC_DIGITAL_SOURCE_TYPE = "http://cv.iptc.org/newscodes/digitalsourcetype/{}"

CLAIM_GENERATOR = "markproof-demo-bot"
CLAIM_GENERATOR_VERSION = "0.2.0"


# --------------------------------------------------------------------------
# A 5x7 bitmap font, written out as pixels so it can be read and edited as
# pixels. Only the glyphs the captions need; unknown characters render blank.
# --------------------------------------------------------------------------
FONT: dict[str, str] = {
    " ": "00000 00000 00000 00000 00000 00000 00000",
    "-": "00000 00000 00000 11111 00000 00000 00000",
    "A": "01110 10001 10001 11111 10001 10001 10001",
    "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110",
    "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111",
    "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111",
    "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "11111 00100 00100 00100 00100 00100 11111",
    "K": "10001 10010 10100 11000 10100 10010 10001",
    "M": "10001 11011 10101 10101 10001 10001 10001",
    "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110",
    "P": "11110 10001 10001 11110 10000 10000 10000",
    "R": "11110 10001 10001 11110 10100 10010 10001",
    "T": "11111 00100 00100 00100 00100 00100 00100",
}

#: Baked into the pixels, not into the metadata — on purpose. The caption
#: survives the CDN that strips the manifest, which is precisely why a visible
#: label is not a substitute for machine-readable provenance.
CAPTIONS = (
    ("AI-GENERATED", 6),
    ("MARKPROOF DEMO", 4),
    ("NOT A PHOTOGRAPH", 3),
)


@dataclass(frozen=True)
class Canvas:
    """A mutable indexed-colour bitmap, one palette index per pixel."""

    width: int
    height: int
    pixels: bytearray

    @classmethod
    def filled(cls, width: int, height: int, index: int) -> Canvas:
        return cls(width, height, bytearray([index]) * (width * height))

    def put(self, x: int, y: int, index: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y * self.width + x] = index


def draw_rings(canvas: Canvas) -> None:
    """Concentric diamonds around the centre — deterministic, no RNG."""
    cx, cy = canvas.width // 2, canvas.height // 2
    for y in range(canvas.height):
        for x in range(canvas.width):
            distance = abs(x - cx) + abs(y - cy)
            canvas.put(x, y, 1 + (distance // 26) % 4)


def draw_frame(canvas: Canvas, inset: int, thickness: int, index: int) -> None:
    """A hairline border, so a stripped asset still looks like a demo asset."""
    for y in range(inset, canvas.height - inset):
        for x in range(inset, canvas.width - inset):
            on_edge = (
                x < inset + thickness
                or x >= canvas.width - inset - thickness
                or y < inset + thickness
                or y >= canvas.height - inset - thickness
            )
            if on_edge:
                canvas.put(x, y, index)


def text_width(text: str, scale: int) -> int:
    """Width in pixels of ``text`` at ``scale``, one blank column between glyphs."""
    return (6 * len(text) - 1) * scale


def draw_text(canvas: Canvas, text: str, top: int, scale: int, index: int) -> None:
    """Render ``text`` horizontally centred, one bitmap pixel to ``scale``²."""
    left = (canvas.width - text_width(text, scale)) // 2
    for position, char in enumerate(text):
        rows = FONT.get(char, FONT[" "]).split()
        for row, bits in enumerate(rows):
            for column, bit in enumerate(bits):
                if bit != "1":
                    continue
                x0 = left + (position * 6 + column) * scale
                y0 = top + row * scale
                for dy in range(scale):
                    for dx in range(scale):
                        canvas.put(x0 + dx, y0 + dy, index)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def encode_png(canvas: Canvas) -> bytes:
    """Indexed PNG, colour type 3, 8 bits per pixel. No ancillary chunks.

    No tIME, no tEXt, no gAMA: nothing in the output depends on the clock or
    the machine, so two people running this script get the same base image.
    """
    raw = bytearray()
    for y in range(canvas.height):
        raw.append(0)  # filter type 0 (None) — keeps the encoder trivial
        raw += canvas.pixels[y * canvas.width : (y + 1) * canvas.width]
    palette = b"".join(bytes(colour) for colour in PALETTE)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 3, 0, 0, 0))
        + _chunk(b"PLTE", palette)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def build_base_image() -> bytes:
    """The one image all three fixtures share. Same pixels, different provenance."""
    canvas = Canvas.filled(WIDTH, HEIGHT, GROUND)
    draw_rings(canvas)
    draw_frame(canvas, inset=18, thickness=3, index=TEXT)
    top = 176
    for text, scale in CAPTIONS:
        draw_text(canvas, text, top=top, scale=scale, index=TEXT)
        top += 7 * scale + 28
    return encode_png(canvas)


# --------------------------------------------------------------------------
# Signing identity
# --------------------------------------------------------------------------
_NOT_BEFORE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
#: Twenty years. A demo fixture that expires is a demo that breaks silently on
#: some morning nobody is watching; c2pa-rs checks the signing certificate's
#: validity window when there is no timestamp authority to anchor it.
_NOT_AFTER = dt.datetime(2046, 1, 1, tzinfo=dt.UTC)

_ORG = "markproof demo-bot (development only)"


def _distinguished_name(common_name: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, _ORG),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _key_usage(**enabled: bool) -> x509.KeyUsage:
    usage = dict.fromkeys(
        (
            "digital_signature",
            "content_commitment",
            "key_encipherment",
            "data_encipherment",
            "key_agreement",
            "key_cert_sign",
            "crl_sign",
            "encipher_only",
            "decipher_only",
        ),
        False,
    )
    usage.update(enabled)
    return x509.KeyUsage(**usage)


def make_dev_chain() -> tuple[bytes, bytes]:
    """A throwaway root + leaf. Returns (PEM chain, PEM private key).

    Two certificates, not one: c2pa-rs rejects a lone self-signed leaf
    ("the certificate is invalid"), because the C2PA certificate profile wants
    an end-entity certificate — CA:false, keyUsage digitalSignature, an
    extended key usage of id-kp-emailProtection — issued by something else.

    The key never leaves this process. Nobody should trust these certificates
    and nothing does: validation reports the manifest as valid but the signer
    as untrusted, which is exactly the state a self-signed demo should be in.
    """
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = _distinguished_name("markproof demo-bot dev root")
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_NOT_BEFORE)
        .not_valid_after(_NOT_AFTER)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_key_usage(key_cert_sign=True, crl_sign=True), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), False)
        .sign(root_key, hashes.SHA256())
    )

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(_distinguished_name("markproof demo-bot signer"))
        .issuer_name(root_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_NOT_BEFORE)
        .not_valid_after(_NOT_AFTER)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(_key_usage(digital_signature=True), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), False
        )
        .sign(root_key, hashes.SHA256())
    )

    chain = leaf.public_bytes(serialization.Encoding.PEM) + root.public_bytes(
        serialization.Encoding.PEM
    )
    key_pem = leaf_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return chain, key_pem


def manifest_for(digital_source_type: str) -> dict[str, object]:
    """One assertion, nothing else — the fixture should test one thing."""
    agent = {"name": CLAIM_GENERATOR, "version": CLAIM_GENERATOR_VERSION}
    return {
        "claim_generator_info": [agent],
        "title": "markproof demo image",
        "format": "image/png",
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": IPTC_DIGITAL_SOURCE_TYPE.format(
                                digital_source_type
                            ),
                            "softwareAgent": agent,
                        }
                    ]
                },
            }
        ],
    }


#: The SDK derives a claim thumbnail from the asset. At the default long edge
#: that JPEG is 118 kB — sixteen times the image it describes, all of it noise
#: in a repository. 256 px keeps a real thumbnail in the manifest at a tenth of
#: the weight.
_SIGNING_SETTINGS = {"builder": {"thumbnail": {"enabled": True, "long_edge": 256}}}


def sign(image: bytes, digital_source_type: str, chain: bytes, key: bytes) -> bytes:
    """Embed a signed manifest into a copy of ``image``."""
    signer_info = c2pa.C2paSignerInfo(
        alg=b"es256",
        sign_cert=chain,
        private_key=key,
        ta_url=None,  # no timestamp authority: one less network dependency
    )
    settings = c2pa.Settings.from_dict(_SIGNING_SETTINGS)
    context = c2pa.Context.builder().with_settings(settings).build()
    signer = c2pa.Signer.from_info(signer_info)
    builder = c2pa.Builder(manifest_for(digital_source_type), context=context)
    destination = io.BytesIO()
    try:
        builder.sign(signer, "image/png", io.BytesIO(image), destination)
    finally:
        builder.close()
        signer.close()
    return destination.getvalue()


def describe(name: str, data: bytes) -> None:
    """Print what the README's provenance table needs."""
    print(f"{name:24} {len(data):>8} bytes  sha256={hashlib.sha256(data).hexdigest()}")


def main() -> None:
    base = build_base_image()
    chain, key = make_dev_chain()

    outputs = {
        "demo-unsigned.png": base,
        "demo-signed.png": sign(base, "trainedAlgorithmicMedia", chain, key),
        "demo-wrongtype.png": sign(base, "algorithmicMedia", chain, key),
    }
    for name, data in outputs.items():
        (HERE / name).write_bytes(data)
        describe(name, data)

    print("\nRead back:")
    for name in outputs:
        path = HERE / name
        reader = c2pa.Reader.try_create(str(path))
        if reader is None:
            print(f"{name:24} no manifest")
            continue
        with reader:
            active = reader.get_active_manifest() or {}
            actions = next(
                (a for a in active.get("assertions", []) if a["label"].startswith("c2pa.actions")),
                {"data": {"actions": [{}]}},
            )
            source_type = actions["data"]["actions"][0].get("digitalSourceType", "—")
            print(
                f"{name:24} state={reader.get_validation_state()} "
                f"embedded={reader.is_embedded()} "
                f"digitalSourceType={source_type.rsplit('/', 1)[-1]}"
            )


if __name__ == "__main__":
    main()
