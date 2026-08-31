#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Generate the golden C2PA media fixture matrix for markproof M2.

Why this script exists
----------------------
markproof's C2PA check (``src/markproof/checks/c2pa_verify.py``) has to answer
two *separate* questions about media served by a live endpoint:

1. Does the asset carry a cryptographically sound C2PA manifest?
2. Does that manifest actually assert
   ``digitalSourceType = trainedAlgorithmicMedia``, i.e. the value that makes
   it an EU AI Act Art. 50 disclosure rather than merely "signed"?

Question 2 is the one no competing tool checks at assertion level, so the
fixtures deliberately include assets that pass question 1 and fail question 2.

Legal constraint (Auflage H2): EVERY byte of media here is our own production.
The images, the audio and the video frames are synthesised from closed-form
integer expressions in this file. Nothing is downloaded, and no third-party
image, sound or video ever enters this directory.

Determinism
-----------
The *base* (unsigned) media are bit-exact reproducible on any platform: the
PNG uses stored (uncompressed) DEFLATE blocks so no zlib version can change
the output, the JPEG encoder runs an all-integer DCT, and the audio is an
integer triangle wave. No timestamps, no RNG, no floating-point rounding
reaches the file bytes.

The *signed* files are NOT byte-reproducible, and cannot be: an ECDSA
signature embeds a fresh random nonce on every run, and c2pa mints a new
manifest UUID each time. Their **properties** are reproducible instead, which
is what the tests assert. See MANIFEST.json: signed assets carry
``"sha256": null`` on purpose.

Usage
-----
    python generate.py            # create anything missing or broken (idempotent)
    python generate.py --force    # re-sign everything from scratch
    python generate.py --verify   # verify existing fixtures, write nothing

Requires the dev venv (``c2pa-python``); ``cryptography`` is only needed for
``--regenerate-test-certs``, which is not part of a normal run.
"""

# This is an operator-facing CLI generator, not shipped library code: printing
# the per-fixture verification table to stdout is the entire point of running it.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import c2pa

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "MANIFEST.json"

# ---------------------------------------------------------------------------
# TEST SIGNING MATERIAL  --  NOT A SECRET, NOT FOR PRODUCTION USE
# ---------------------------------------------------------------------------
# The private key below is deliberately committed in plain text. It exists so
# that anyone can regenerate these fixtures offline and get the same trust
# decisions. It is safe to publish ONLY because:
#
#   * the root CA is self-signed and appears in no trust store anywhere;
#   * markproof never treats this CA as trusted at runtime -- it is injected
#     as an explicit trust anchor by the tests, and nowhere else;
#   * the certificates are scoped to a subject that screams NOT FOR PRODUCTION.
#
# Never reuse this key to sign anything real. Any C2PA manifest signed with it
# is, by construction, worthless as provenance evidence.
#
# The chain is end-entity first, then root, as c2pa expects. The end-entity
# cert carries keyUsage=digitalSignature and EKU emailProtection +
# documentSigning, which is what the C2PA certificate profile requires of a
# claim signer. Regenerate with --regenerate-test-certs (see _regen_certs).
# ---------------------------------------------------------------------------

TEST_CERT_CHAIN_PEM = """\
-----BEGIN CERTIFICATE-----
MIICUjCCAfmgAwIBAgINTUFSS1BST09GAAAAAjAKBggqhkjOPQQDAjBtMQswCQYD
VQQGEwJERTEgMB4GA1UECgwXbWFya3Byb29mIHRlc3QgZml4dHVyZXMxGzAZBgNV
BAsMEk5PVCBGT1IgUFJPRFVDVElPTjEfMB0GA1UEAwwWbWFya3Byb29mIHRlc3Qg
cm9vdCBDQTAeFw0yNjAxMDEwMDAwMDBaFw0zNjAxMDEwMDAwMDBaMGwxCzAJBgNV
BAYTAkRFMSAwHgYDVQQKDBdtYXJrcHJvb2YgdGVzdCBmaXh0dXJlczEbMBkGA1UE
CwwSTk9UIEZPUiBQUk9EVUNUSU9OMR4wHAYDVQQDDBVtYXJrcHJvb2YgdGVzdCBz
aWduZXIwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAS1oQS2yq36Fab7nrOTkjco
TUBOnZSGtwZBFFehbxLoShi769l+UlhnB1RCvVMOpNKe562HOoKmLoBL48CONMnW
o38wfTAMBgNVHRMBAf8EAjAAMA4GA1UdDwEB/wQEAwIHgDAdBgNVHSUEFjAUBggr
BgEFBQcDBAYIKwYBBQUHAyQwHQYDVR0OBBYEFDOccXzSYxKQKtfcE7CQ7b593mS8
MB8GA1UdIwQYMBaAFM/KR5w7O2zJe8oHYQ8lDFNsh6m1MAoGCCqGSM49BAMCA0cA
MEQCIEWVQQYe6rvJhYPTV8E6rb94+M6JWTvrhHLgbKwhZjtBAiBqV1MTmWfGIaLc
l5OJ1OlbGXyoKk+KixTfxhOYGeR+cw==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICFzCCAb2gAwIBAgINTUFSS1BST09GAAAAATAKBggqhkjOPQQDAjBtMQswCQYD
VQQGEwJERTEgMB4GA1UECgwXbWFya3Byb29mIHRlc3QgZml4dHVyZXMxGzAZBgNV
BAsMEk5PVCBGT1IgUFJPRFVDVElPTjEfMB0GA1UEAwwWbWFya3Byb29mIHRlc3Qg
cm9vdCBDQTAeFw0yNjAxMDEwMDAwMDBaFw0zNjAxMDEwMDAwMDBaMG0xCzAJBgNV
BAYTAkRFMSAwHgYDVQQKDBdtYXJrcHJvb2YgdGVzdCBmaXh0dXJlczEbMBkGA1UE
CwwSTk9UIEZPUiBQUk9EVUNUSU9OMR8wHQYDVQQDDBZtYXJrcHJvb2YgdGVzdCBy
b290IENBMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2+SqjSou5EfTwSUUCJE0
MxnrisdkN+lN1JQKE+GTkGil0Uak2mHfFDaOR8bsynjCpQRTca4EgjfppGv8Ripq
kKNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAYYwHQYDVR0OBBYE
FM/KR5w7O2zJe8oHYQ8lDFNsh6m1MAoGCCqGSM49BAMCA0gAMEUCICZqo/9Z46C8
r/k4wXV1nWqv/lauYKARMrNjnFayzIGnAiEAtNfdOYspLy5LSiyMYEqNE7PD6BUz
cRXV0bgZPM+GFwM=
-----END CERTIFICATE-----
"""

# NOT A SECRET. Test-only ECDSA P-256 private key. See the banner above.
TEST_PRIVATE_KEY_PEM = """\
-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgGis8TV5vcIGSo7TF
1uf4CRorPE1eb3CBkqO0xdbn+AmhRANCAAS1oQS2yq36Fab7nrOTkjcoTUBOnZSG
twZBFFehbxLoShi769l+UlhnB1RCvVMOpNKe562HOoKmLoBL48CONMnW
-----END PRIVATE KEY-----
"""

def _split_pem_certs(pem: str) -> list[str]:
    """Split a PEM bundle into complete, individually parseable certificates."""
    end = "-----END CERTIFICATE-----"
    return [part.lstrip() + end + "\n" for part in pem.split(end) if "BEGIN CERTIFICATE" in part]


# The root CA on its own; tests inject this as an explicit C2PA trust anchor
# so that a correctly signed fixture reaches validation state "Trusted".
TEST_ROOT_CA_PEM = _split_pem_certs(TEST_CERT_CHAIN_PEM)[1]

# ---------------------------------------------------------------------------
# IPTC digital source types (the Art. 50 vocabulary)
# ---------------------------------------------------------------------------
IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"

#: The only value that satisfies EU AI Act Art. 50(2) for synthetic media.
DST_TRAINED = IPTC + "trainedAlgorithmicMedia"
#: Rule-based/procedural generation. NOT AI-generated -> must NOT satisfy Art. 50.
#: This is the hardest near-miss: one vocabulary entry away from compliant.
DST_ALGORITHMIC = IPTC + "algorithmicMedia"
#: Claims to be a camera photograph. The blunt negative case.
DST_CAPTURE = IPTC + "digitalCapture"
#: Human-authored composite that *contains* AI-generated material. Genuinely
#: ambiguous under Art. 50; recorded here so the check has to take a position.
DST_COMPOSITE = IPTC + "compositeWithTrainedAlgorithmicMedia"

IMG_W, IMG_H = 64, 64
VIDEO_FRAMES = 5


# ===========================================================================
# Synthetic image content (our own production, closed-form, integer-only)
# ===========================================================================
def _pixel(x: int, y: int, w: int, h: int, phase: int = 0) -> tuple[int, int, int]:
    """Deterministic synthetic RGB pattern: gradient, border and centre block.

    Pure integer arithmetic, so identical on every platform. ``phase`` shifts
    the pattern to give the video distinguishable frames.
    """
    if x < 3 or y < 3 or x >= w - 3 or y >= h - 3:
        return (16, 16, 16)  # dark border
    r = (x * 255) // (w - 1)
    g = (y * 255) // (h - 1)
    b = ((x + y + phase) * 6) % 256
    if w // 4 <= x < 3 * w // 4 and h // 4 <= y < 3 * h // 4:
        return (255 - r, (g + 128) % 256, 200)  # centre block
    return (r, g, b)


def rgb_bytes(w: int, h: int, phase: int = 0) -> bytes:
    out = bytearray()
    for y in range(h):
        for x in range(w):
            out += bytes(_pixel(x, y, w, h, phase))
    return bytes(out)


# ===========================================================================
# PNG writer -- stored DEFLATE, so output never depends on the zlib version
# ===========================================================================
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _stored_zlib(raw: bytes) -> bytes:
    """zlib stream using only stored (BTYPE=00) blocks -> byte-exact anywhere."""
    out = bytearray(b"\x78\x01")
    i, n = 0, len(raw)
    while True:
        block = raw[i : i + 65535]
        i += len(block)
        final = 1 if i >= n else 0
        out += bytes([final]) + struct.pack("<HH", len(block), 0xFFFF ^ len(block)) + block
        if final:
            break
    out += struct.pack(">I", zlib.adler32(raw) & 0xFFFFFFFF)
    return bytes(out)


def _png_raw_scanlines(w: int, h: int, phase: int = 0) -> bytes:
    """Filter-type-0 scanlines (no filtering), i.e. plain RGB rows."""
    out = bytearray()
    for y in range(h):
        out.append(0)
        for x in range(w):
            out += bytes(_pixel(x, y, w, h, phase))
    return bytes(out)


def make_png(w: int = IMG_W, h: int = IMG_H) -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit truecolour RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", _stored_zlib(_png_raw_scanlines(w, h)))
        + _png_chunk(b"IEND", b"")
    )


def png_patch_pixels(data: bytes, mutate: Callable[[bytes], bytes]) -> bytes:
    """Rewrite the IDAT payload in place, fixing adler32 and every chunk CRC.

    Only works because :func:`_stored_zlib` keeps the pixel bytes uncompressed
    and at fixed offsets, so the replacement is guaranteed to be the same
    length. The result is a fully well-formed PNG whose pixels genuinely
    differ -- which is exactly what "tampered" has to mean.
    """
    pos, out = 8, bytearray(data[:8])
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        if tag == b"IDAT":
            raw = bytearray()
            blocks: list[tuple[int, int]] = []
            j = 2  # skip the 2-byte zlib header
            while True:
                final = payload[j] & 1
                blen = struct.unpack("<H", payload[j + 1 : j + 3])[0]
                blocks.append((j + 5, blen))
                raw += payload[j + 5 : j + 5 + blen]
                j += 5 + blen
                if final:
                    break
            new_raw = mutate(bytes(raw))
            if len(new_raw) != len(raw):
                raise ValueError("pixel mutation must preserve length")
            buf = bytearray(payload)
            k = 0
            for off, blen in blocks:
                buf[off : off + blen] = new_raw[k : k + blen]
                k += blen
            buf[-4:] = struct.pack(">I", zlib.adler32(new_raw) & 0xFFFFFFFF)
            payload = bytes(buf)
        out += _png_chunk(tag, payload)
        pos += 12 + length
    return bytes(out)


# ===========================================================================
# Baseline JPEG encoder -- 4:4:4, all-integer DCT, no third-party code
# ===========================================================================
ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
]  # fmt: skip

_Q_LUM = [
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
]  # fmt: skip

_Q_CHR = [
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
]  # fmt: skip

# ITU-T T.81 Annex K typical Huffman tables.
_DC_LUM_BITS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
_DC_CHR_BITS = [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
_DC_VALS = list(range(12))
_AC_LUM_BITS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D]
_AC_CHR_BITS = [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77]
_AC_LUM_VALS = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
    0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
    0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
    0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
    0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
    0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
    0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
    0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
    0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
    0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA,
]  # fmt: skip
_AC_CHR_VALS = [
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41,
    0x51, 0x07, 0x61, 0x71, 0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91,
    0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0, 0x15, 0x62, 0x72, 0xD1,
    0x0A, 0x16, 0x24, 0x34, 0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26,
    0x27, 0x28, 0x29, 0x2A, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44,
    0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58,
    0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74,
    0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A,
    0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4,
    0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
    0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA,
    0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF2, 0xF3, 0xF4,
    0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA,
]  # fmt: skip

_DCT_SHIFT = 14


def _dct_table() -> list[list[int]]:
    """A[x][u] = round(c(u) * cos((2x+1)u*pi/16) * 2**14), as integers.

    Rounding to 14 bits is far coarser than any libm's error, so the table --
    and therefore every JPEG this script writes -- is identical on every
    platform even though it is seeded from floating-point cosines.
    """
    scale = 1 << _DCT_SHIFT
    table = [[0] * 8 for _ in range(8)]
    for x in range(8):
        for u in range(8):
            cu = (1.0 / math.sqrt(2.0)) if u == 0 else 1.0
            table[x][u] = round(cu * math.cos((2 * x + 1) * u * math.pi / 16.0) * scale)
    return table


_A = _dct_table()
_DCT_DEN = 4 << (2 * _DCT_SHIFT)  # the 1/4 prefactor plus both 2**14 scalings


def _round_div(n: int, d: int) -> int:
    """Round-half-away-from-zero integer division (d > 0)."""
    return (2 * n + d) // (2 * d) if n >= 0 else -((-2 * n + d) // (2 * d))


def _huffman(bits: Sequence[int], vals: Sequence[int]) -> dict[int, tuple[int, int]]:
    code, k, table = 0, 0, {}
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            table[vals[k]] = (code, length)
            k += 1
            code += 1
        code <<= 1
    return table


def _scaled_q(base: Sequence[int], quality: int) -> list[int]:
    q = max(1, min(100, quality))
    s = 5000 // q if q < 50 else 200 - 2 * q
    return [min(255, max(1, (v * s + 50) // 100)) for v in base]


class _BitWriter:
    def __init__(self) -> None:
        self.buf = bytearray()
        self._acc = 0
        self._n = 0

    def write(self, code: int, length: int) -> None:
        for i in range(length - 1, -1, -1):
            self._acc = (self._acc << 1) | ((code >> i) & 1)
            self._n += 1
            if self._n == 8:
                self.buf.append(self._acc)
                if self._acc == 0xFF:
                    self.buf.append(0x00)  # byte stuffing
                self._acc = 0
                self._n = 0

    def flush(self) -> None:
        while self._n:
            self.write(1, 1)


def _magnitude(v: int) -> int:
    a, n = abs(v), 0
    while a:
        n += 1
        a >>= 1
    return n


def make_jpeg(w: int = IMG_W, h: int = IMG_H, phase: int = 0, quality: int = 80) -> bytes:
    """Baseline sequential JPEG, 4:4:4, written from scratch."""
    lq, cq = _scaled_q(_Q_LUM, quality), _scaled_q(_Q_CHR, quality)

    # RGB -> YCbCr with the standard fixed-point coefficients (16-bit scale).
    y_p = [0] * (w * h)
    cb_p = [0] * (w * h)
    cr_p = [0] * (w * h)
    for py in range(h):
        for px in range(w):
            r, g, b = _pixel(px, py, w, h, phase)
            i = py * w + px
            y_p[i] = ((19595 * r + 38470 * g + 7471 * b + 32768) >> 16) - 128
            cb_p[i] = ((-11056 * r - 21712 * g + 32768 * b + 8421376) >> 16) - 128
            cr_p[i] = ((32768 * r - 27440 * g - 5328 * b + 8421376) >> 16) - 128

    out = bytearray(b"\xff\xd8")
    out += b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    out += b"\xff\xdb" + struct.pack(">H", 67) + b"\x00" + bytes(lq[ZIGZAG[i]] for i in range(64))
    out += b"\xff\xdb" + struct.pack(">H", 67) + b"\x01" + bytes(cq[ZIGZAG[i]] for i in range(64))
    out += b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", h, w) + b"\x03"
    out += b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"  # 3 components, no subsampling
    for cls, tid, bits, vals in (
        (0, 0, _DC_LUM_BITS, _DC_VALS),
        (1, 0, _AC_LUM_BITS, _AC_LUM_VALS),
        (0, 1, _DC_CHR_BITS, _DC_VALS),
        (1, 1, _AC_CHR_BITS, _AC_CHR_VALS),
    ):
        out += (
            b"\xff\xc4"
            + struct.pack(">H", 3 + 16 + len(vals))
            + bytes([cls << 4 | tid])
            + bytes(bits)
            + bytes(vals)
        )
    out += b"\xff\xda" + struct.pack(">H", 12) + b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"

    dc_l, ac_l = _huffman(_DC_LUM_BITS, _DC_VALS), _huffman(_AC_LUM_BITS, _AC_LUM_VALS)
    dc_c, ac_c = _huffman(_DC_CHR_BITS, _DC_VALS), _huffman(_AC_CHR_BITS, _AC_CHR_VALS)
    bw = _BitWriter()
    pred = [0, 0, 0]

    def encode_block(plane: list[int], bx: int, by: int, q: list[int],
                     dc_t: dict[int, tuple[int, int]], ac_t: dict[int, tuple[int, int]],
                     ci: int) -> None:
        # Gather one 8x8 block, clamping at the edges.
        blk = [[plane[min(by + yy, h - 1) * w + min(bx + xx, w - 1)] for xx in range(8)]
               for yy in range(8)]
        # Exact integer 2-D DCT, separable: rows then columns, no rounding
        # until the final quantisation step.
        tmp = [[sum(blk[yy][xx] * _A[xx][u] for xx in range(8)) for u in range(8)]
               for yy in range(8)]
        zz = [0] * 64
        for i in range(64):
            v, u = divmod(ZIGZAG[i], 8)
            num = sum(tmp[yy][u] * _A[yy][v] for yy in range(8))
            zz[i] = _round_div(num, _DCT_DEN * q[ZIGZAG[i]])

        diff = zz[0] - pred[ci]
        pred[ci] = zz[0]
        n = _magnitude(diff)
        code, ln = dc_t[n]
        bw.write(code, ln)
        if n:
            bw.write(diff if diff > 0 else diff + (1 << n) - 1, n)

        run = 0
        for k in range(1, 64):
            if zz[k] == 0:
                run += 1
                continue
            while run > 15:
                code, ln = ac_t[0xF0]  # ZRL
                bw.write(code, ln)
                run -= 16
            n = _magnitude(zz[k])
            code, ln = ac_t[(run << 4) | n]
            bw.write(code, ln)
            bw.write(zz[k] if zz[k] > 0 else zz[k] + (1 << n) - 1, n)
            run = 0
        if run:
            code, ln = ac_t[0x00]  # EOB
            bw.write(code, ln)

    for by in range(0, h, 8):
        for bx in range(0, w, 8):
            encode_block(y_p, bx, by, lq, dc_l, ac_l, 0)
            encode_block(cb_p, bx, by, cq, dc_c, ac_c, 1)
            encode_block(cr_p, bx, by, cq, dc_c, ac_c, 2)
    bw.flush()
    return bytes(out + bw.buf + b"\xff\xd9")


def jpeg_primary_dqt_offset(data: bytes) -> int:
    """Offset of the first coefficient byte of the primary image's last DQT.

    Walks the marker segments properly instead of scanning for ``FFDB``. That
    matters: a signed asset contains a C2PA manifest (and possibly a JPEG
    thumbnail) *before* the primary image, and blindly patching the first
    ``FFDB`` corrupts the manifest instead of the picture.
    """
    pos, last = 2, None
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if marker == 0xD9:
            break
        length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
        if marker == 0xDB:
            last = pos + 4 + 1  # +1 skips the Pq/Tq precision/id byte
        if marker == 0xDA:
            break  # start of the primary scan: stop here
        pos += 2 + length
    if last is None:
        raise ValueError("no DQT segment found")
    return last


# ===========================================================================
# WAV writer -- integer triangle wave, 16-bit mono PCM
# ===========================================================================
def make_wav(seconds: int = 1, rate: int = 8000, period: int = 18, amp: int = 12000) -> bytes:
    """Mono 16-bit PCM triangle wave (~444 Hz at 8 kHz), pure integer maths."""
    n = rate * seconds
    frames = bytearray()
    half = period // 2
    for i in range(n):
        p = i % period
        tri = p if p < half else period - p  # 0..half..0
        v = (tri * 2 * amp) // half - amp  # scale to -amp..+amp
        env = min(1000, i, n - i)  # short fade in/out, avoids clicks
        frames += struct.pack("<h", (v * env) // 1000)
    data = bytes(frames)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    body = (
        b"WAVE"
        + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        + b"data" + struct.pack("<I", len(data)) + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def riff_data_range(data: bytes) -> tuple[int, int]:
    """(offset, length) of the WAVE ``data`` chunk payload, by chunk walk."""
    pos = 12
    while pos + 8 <= len(data):
        tag = data[pos : pos + 4]
        length = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        if tag == b"data":
            return pos + 8, length
        pos += 8 + length + (length & 1)  # chunks are word-aligned
    raise ValueError("no data chunk found")


# ===========================================================================
# MP4 writer -- Motion JPEG in ISO-BMFF, frames from our own JPEG encoder
# ===========================================================================
def _box(tag: bytes, *parts: bytes) -> bytes:
    payload = b"".join(parts)
    return struct.pack(">I", 8 + len(payload)) + tag + payload


def _fbox(tag: bytes, version: int, flags: int, *parts: bytes) -> bytes:
    return _box(tag, bytes([version]) + flags.to_bytes(3, "big"), *parts)


def make_mp4(w: int = IMG_W, h: int = IMG_H, n: int = VIDEO_FRAMES,
             timescale: int = 600, dur: int = 120) -> bytes:
    """A real, decodable MJPEG video: every frame is one of our own JPEGs."""
    frames = [make_jpeg(w, h, phase=f * 16) for f in range(n)]
    duration = n * dur
    unity = struct.pack(">9i", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)

    ftyp = _box(b"ftyp", b"isom", struct.pack(">I", 512), b"isomiso2mp41qt  ")
    mvhd = _fbox(b"mvhd", 0, 0,
                 struct.pack(">IIII", 0, 0, timescale, duration),
                 struct.pack(">i", 0x00010000) + struct.pack(">h", 0x0100)
                 + b"\x00\x00" + b"\x00" * 8,
                 unity + b"\x00" * 24 + struct.pack(">I", 2))
    tkhd = _fbox(b"tkhd", 0, 7,
                 struct.pack(">IIIII", 0, 0, 1, 0, duration) + b"\x00" * 8,
                 struct.pack(">hhhh", 0, 0, 0, 0) + unity,
                 struct.pack(">II", w << 16, h << 16))
    mdhd = _fbox(b"mdhd", 0, 0,
                 struct.pack(">IIII", 0, 0, timescale, duration) + struct.pack(">HH", 0x55C4, 0))
    hdlr = _fbox(b"hdlr", 0, 0, struct.pack(">I", 0) + b"vide" + b"\x00" * 12 + b"VideoHandler\x00")
    vmhd = _fbox(b"vmhd", 0, 1, struct.pack(">HHHH", 0, 0, 0, 0))
    dinf = _box(b"dinf", _fbox(b"dref", 0, 0, struct.pack(">I", 1) + _fbox(b"url ", 0, 1)))

    name = b"Motion JPEG"
    compressor = bytes([len(name)]) + name + b"\x00" * (31 - len(name))
    sample_entry = _box(b"jpeg",
                        b"\x00" * 6 + struct.pack(">H", 1) + b"\x00" * 16,
                        struct.pack(">HH", w, h) + struct.pack(">II", 0x00480000, 0x00480000),
                        struct.pack(">I", 0) + struct.pack(">H", 1) + compressor,
                        struct.pack(">H", 0x0018) + struct.pack(">h", -1))
    stsd = _fbox(b"stsd", 0, 0, struct.pack(">I", 1) + sample_entry)
    stts = _fbox(b"stts", 0, 0, struct.pack(">I", 1) + struct.pack(">II", n, dur))
    stss = _fbox(b"stss", 0, 0,
                 struct.pack(">I", n) + b"".join(struct.pack(">I", i + 1) for i in range(n)))
    stsc = _fbox(b"stsc", 0, 0, struct.pack(">I", 1) + struct.pack(">III", 1, n, 1))
    stsz = _fbox(b"stsz", 0, 0,
                 struct.pack(">II", 0, n) + b"".join(struct.pack(">I", len(s)) for s in frames))

    def build_moov(chunk_offset: int) -> bytes:
        stco = _fbox(b"stco", 0, 0, struct.pack(">I", 1) + struct.pack(">I", chunk_offset))
        stbl = _box(b"stbl", stsd, stts, stss, stsc, stsz, stco)
        minf = _box(b"minf", vmhd, dinf, stbl)
        mdia = _box(b"mdia", mdhd, hdlr, minf)
        return _box(b"moov", mvhd, _box(b"trak", tkhd, mdia))

    # moov has a fixed size, so one dry run is enough to learn the mdat offset.
    moov = build_moov(len(ftyp) + len(build_moov(0)) + 8)
    return ftyp + moov + _box(b"mdat", b"".join(frames))


def bmff_box_range(data: bytes, want: bytes) -> tuple[int, int]:
    """(offset, length) of a top-level ISO-BMFF box payload."""
    pos = 0
    while pos + 8 <= len(data):
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header = 16
        elif size == 0:
            size = len(data) - pos
        if tag == want:
            return pos + header, size - header
        pos += size
    raise ValueError(f"box {want!r} not found")


# ===========================================================================
# C2PA signing and verification
# ===========================================================================
def build_signer() -> c2pa.Signer:
    return c2pa.Signer.from_info(
        c2pa.C2paSignerInfo(
            alg=b"es256",
            sign_cert=TEST_CERT_CHAIN_PEM.encode(),
            private_key=TEST_PRIVATE_KEY_PEM.encode(),
            ta_url=None,  # no RFC 3161 timestamp: keeps this fully offline
        )
    )


def _reader_context() -> Any:
    """Reader context that trusts our test root, so a good fixture is Trusted."""
    settings = c2pa.Settings.from_dict(
        {"verify": {"verify_trust": True}, "trust": {"trust_anchors": TEST_ROOT_CA_PEM}}
    )
    return c2pa.ContextBuilder().with_settings(settings).build()


def _builder_context() -> Any:
    """Builder context with thumbnails off -- they triple the fixture size and
    add nothing to an assertion-level test."""
    settings = c2pa.Settings.from_dict({"builder": {"thumbnail": {"enabled": False}}})
    return c2pa.ContextBuilder().with_settings(settings).build()


def sign_asset(src: Path, dst: Path, fmt: str, assertions: list[dict[str, Any]],
               claim_version: int | None = None) -> None:
    manifest: dict[str, Any] = {
        "claim_generator_info": [{"name": "markproof-fixtures", "version": "0.1.0"}],
        "title": dst.name,
        "format": fmt,
        "assertions": assertions,
    }
    if claim_version is not None:
        manifest["claim_version"] = claim_version
    if dst.exists():
        dst.unlink()  # c2pa refuses to overwrite
    c2pa.Builder(manifest, context=_builder_context()).sign_file(src, dst, build_signer())


def actions_assertion(source_type: str | None,
                      action: str = "c2pa.created") -> list[dict[str, Any]]:
    entry: dict[str, Any] = {"action": action}
    if source_type is not None:
        entry["digitalSourceType"] = source_type
    return [{"label": "c2pa.actions.v2", "data": {"actions": [entry]}}]


def inspect_asset(path: Path) -> dict[str, Any]:
    """Read a fixture back and report what C2PA actually says about it.

    NOTE for the check implementation: ``Reader.is_valid`` is NOT a validation
    result -- it reports whether the Reader object is still open. It returns
    True for a provably tampered asset. Always use ``get_validation_state()``.
    """
    try:
        reader = c2pa.Reader(str(path), context=_reader_context())
    except Exception as exc:
        return {"manifest": False, "state": None, "source_types": [],
                "failures": [], "error": f"{type(exc).__name__}: {exc}"}
    state = str(reader.get_validation_state())
    results = reader.get_validation_results() or {}
    active = results.get("activeManifest", {}) or {}
    failures = sorted({f.get("code") for f in active.get("failure", []) if f.get("code")})
    source_types: list[str] = []
    read_error: str | None = None
    try:
        manifest = reader.get_active_manifest() or {}
        for assertion in manifest.get("assertions", []) or []:
            if not str(assertion.get("label", "")).startswith("c2pa.actions"):
                continue
            for act in (assertion.get("data") or {}).get("actions", []) or []:
                if act.get("digitalSourceType"):
                    source_types.append(act["digitalSourceType"])
    except Exception as exc:
        # A badly damaged manifest can still validate far enough to yield a
        # state but fail to deserialise. Surface it rather than reporting an
        # empty assertion list, which would look like "signed but silent".
        read_error = f"could not read assertions: {type(exc).__name__}: {exc}"
    return {"manifest": True, "state": state, "source_types": source_types,
            "failures": failures, "error": read_error}


# ===========================================================================
# The fixture matrix
# ===========================================================================
FORMATS = {
    "png": {"mime": "image/png", "label": "PNG (truecolour, stored DEFLATE)"},
    "jpg": {"mime": "image/jpeg", "label": "JPEG (baseline, 4:4:4, q80)"},
    "mp4": {"mime": "video/mp4", "label": "MP4 (ISO-BMFF, Motion JPEG, 5 frames)"},
    "wav": {"mime": "audio/wav", "label": "WAV (16-bit mono PCM, 8 kHz)"},
}

BASE_BUILDERS: dict[str, Callable[[], bytes]] = {
    "png": make_png,
    "jpg": lambda: make_jpeg(IMG_W, IMG_H, phase=0),
    "mp4": make_mp4,
    "wav": make_wav,
}


def _tamper(ext: str, data: bytes) -> bytes:
    """Alter the *media payload* of a signed asset, never its manifest.

    Each format is patched through a structural walk so the file stays
    well-formed and still decodes; only the C2PA hash binding breaks.
    """
    if ext == "png":
        def mutate(raw: bytes) -> bytes:
            buf = bytearray(raw)
            # Invert a horizontal band of real pixels (skip filter bytes).
            for row in range(8, 24):
                start = row * (1 + IMG_W * 3) + 1
                for i in range(start, start + IMG_W * 3):
                    buf[i] = 255 - buf[i]
            return bytes(buf)
        return png_patch_pixels(data, mutate)

    if ext == "jpg":
        buf = bytearray(data)
        off = jpeg_primary_dqt_offset(bytes(buf))
        for i in range(off, off + 16):  # rewrite quantisation coefficients
            buf[i] = max(1, min(255, (buf[i] * 5 + 11) % 255))
        return bytes(buf)

    if ext == "wav":
        buf = bytearray(data)
        start, length = riff_data_range(bytes(buf))
        for i in range(start, start + min(400, length)):
            buf[i] = (buf[i] + 37) % 256
        return bytes(buf)

    if ext == "mp4":
        buf = bytearray(data)
        start, length = bmff_box_range(bytes(buf), b"mdat")
        off = jpeg_primary_dqt_offset(bytes(buf[start : start + length]))
        for i in range(start + off, start + off + 16):
            buf[i] = max(1, min(255, (buf[i] * 5 + 11) % 255))
        return bytes(buf)

    raise ValueError(f"no tamper strategy for {ext}")


def fixture_plan() -> list[dict[str, Any]]:
    """The full matrix: 4 states x 4 formats, plus PNG-only edge cases."""
    plan: list[dict[str, Any]] = []
    for ext in FORMATS:
        plan += [
            {
                "filename": f"signed-valid.{ext}", "ext": ext, "state": "signed-valid",
                "source_type": DST_TRAINED, "expected_valid": True,
                "expected_state": "Trusted", "expected_failures": [],
                "how": f"{FORMATS[ext]['label']} synthesised by generate.py, then signed "
                       f"with the test CA carrying c2pa.actions.v2 "
                       f"c2pa.created/digitalSourceType=trainedAlgorithmicMedia.",
                "why": "The only fully Art. 50-compliant case: sound manifest AND the "
                       "correct AI-generation assertion. Must PASS.",
            },
            {
                "filename": f"signed-wrong-type.{ext}", "ext": ext, "state": "signed-wrong-type",
                "source_type": DST_ALGORITHMIC, "expected_valid": True,
                "expected_state": "Trusted", "expected_failures": [],
                "how": f"As signed-valid.{ext}, but the assertion says "
                       f"digitalSourceType=algorithmicMedia.",
                "why": "THE critical negative. Cryptographically flawless and fully "
                       "trusted, yet not Art. 50 compliant: algorithmicMedia means "
                       "rule-based/procedural output, not a trained model. A check that "
                       "only verifies the signature passes this and is wrong.",
            },
            {
                "filename": f"unsigned.{ext}", "ext": ext, "state": "unsigned",
                "source_type": None, "expected_valid": False,
                "expected_state": None, "expected_failures": [],
                "how": f"{FORMATS[ext]['label']} synthesised by generate.py and left "
                       f"untouched. No C2PA data of any kind.",
                "why": "Baseline: media with no provenance at all. c2pa.Reader raises "
                       "ManifestNotFound here rather than returning an invalid state, so "
                       "the check must catch that instead of relying on a return value.",
            },
            {
                "filename": f"tampered.{ext}", "ext": ext, "state": "tampered",
                "source_type": DST_TRAINED, "expected_valid": False,
                "expected_state": "Invalid",
                "expected_failures": ["assertion.bmffHash.mismatch"] if ext == "mp4"
                                     else ["assertion.dataHash.mismatch"],
                "how": f"signed-valid.{ext} with its media payload altered afterwards "
                       f"(see _tamper()); the manifest is left byte-identical.",
                "why": "The manifest still claims trainedAlgorithmicMedia and the "
                       "signature still verifies, but the content no longer matches the "
                       "hash. A correct check must reject this despite the good assertion.",
            },
        ]

    plan += [
        {
            "filename": "signed-wrong-type-capture.png", "ext": "png",
            "state": "signed-wrong-type", "source_type": DST_CAPTURE,
            "expected_valid": True, "expected_state": "Trusted", "expected_failures": [],
            "how": "As signed-valid.png, but digitalSourceType=digitalCapture.",
            "why": "Synthetic media positively claiming to be a camera photograph -- the "
                   "blunt misdeclaration, as opposed to the algorithmicMedia near-miss.",
        },
        {
            "filename": "signed-composite.png", "ext": "png",
            "state": "signed-edge-case", "source_type": DST_COMPOSITE,
            "expected_valid": True, "expected_state": "Trusted", "expected_failures": [],
            "how": "As signed-valid.png, but "
                   "digitalSourceType=compositeWithTrainedAlgorithmicMedia.",
            "why": "Human-authored composite containing AI-generated parts. Art. 50(2) "
                   "covers generated OR manipulated content, so whether this must be "
                   "disclosed is a policy call -- the fixture forces the check to make it "
                   "explicitly rather than by accident.",
        },
        {
            "filename": "signed-no-source-type.png", "ext": "png",
            "state": "signed-no-source-type", "source_type": None,
            "expected_valid": True, "expected_state": "Trusted", "expected_failures": [],
            "claim_version": 1,
            "how": "signed with a c2pa.created action carrying NO digitalSourceType. "
                   "Requires claim_version=1: at claim v2 the SDK rejects this as "
                   "assertion.action.malformed (verified, see README).",
            "why": "A manifest that is present, trusted and silent on AI provenance. "
                   "Distinct from both unsigned and wrong-type, and common in the wild "
                   "from older/minimal signers. Must FAIL the Art. 50 check without "
                   "being reported as a broken signature.",
        },
    ]
    return plan


# ===========================================================================
# Generation driver
# ===========================================================================
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matches_expectation(spec: dict[str, Any], info: dict[str, Any]) -> tuple[bool, str]:
    if not spec["expected_valid"] and spec["state"] == "unsigned":
        if info["manifest"]:
            return False, "expected no manifest, but one was found"
        return True, "no manifest (as expected)"
    if not info["manifest"]:
        return False, f"expected a manifest, got {info['error']}"
    if info["state"] != spec["expected_state"]:
        return False, f"state {info['state']!r} != expected {spec['expected_state']!r}"
    if spec["expected_failures"] and set(info["failures"]) != set(spec["expected_failures"]):
        return False, f"failures {info['failures']} != expected {spec['expected_failures']}"
    want = spec["source_type"]
    got = info["source_types"]
    if spec["state"] == "tampered":
        pass  # payload broken; the assertion itself is still whatever we signed
    if want is None and got:
        return False, f"expected no digitalSourceType, got {got}"
    if want is not None and want not in got:
        return False, f"digitalSourceType {got} does not contain {want}"
    return True, f"state={info['state']} dst={[s.rsplit('/', 1)[-1] for s in got]}"


def generate(force: bool, verify_only: bool) -> int:
    plan = fixture_plan()
    base_cache: dict[str, bytes] = {}
    failures = 0
    records: list[dict[str, Any]] = []

    for spec in plan:
        ext = spec["ext"]
        path = HERE / spec["filename"]
        signed = spec["state"] != "unsigned"

        if not verify_only and (force or not path.exists()):
            if ext not in base_cache:
                base_cache[ext] = BASE_BUILDERS[ext]()
            base = base_cache[ext]

            if spec["state"] == "unsigned":
                path.write_bytes(base)
            else:
                tmp = HERE / f".tmp-base.{ext}"
                tmp.write_bytes(base)
                try:
                    if spec["state"] == "tampered":
                        staging = HERE / f".tmp-signed.{ext}"
                        sign_asset(tmp, staging, FORMATS[ext]["mime"],
                                   actions_assertion(spec["source_type"]))
                        path.write_bytes(_tamper(ext, staging.read_bytes()))
                        staging.unlink()
                    else:
                        sign_asset(tmp, path, FORMATS[ext]["mime"],
                                   actions_assertion(spec["source_type"]),
                                   claim_version=spec.get("claim_version"))
                finally:
                    tmp.unlink(missing_ok=True)

        if not path.exists():
            print(f"  MISSING  {spec['filename']}")
            failures += 1
            continue

        info = inspect_asset(path)
        ok, detail = _matches_expectation(spec, info)
        print(f"  {'OK  ' if ok else 'FAIL'}     {spec['filename']:32s} {detail}")
        if not ok:
            failures += 1

        records.append({
            "filename": spec["filename"],
            "state": spec["state"],
            "format": FORMATS[ext]["mime"],
            # Signed assets are not byte-reproducible (fresh ECDSA nonce and a
            # fresh manifest UUID per run), so pinning a hash would guarantee a
            # false alarm. Their *properties* are pinned instead.
            "sha256": None if signed else sha256(path),
            "sha256_note": ("omitted: ECDSA nonce and manifest UUID differ on every run"
                            if signed else "stable: base media are bit-exact reproducible"),
            "size_bytes": path.stat().st_size,
            "expected_valid": spec["expected_valid"],
            "expected_source_type": spec["source_type"],
            "expected_validation_state": spec["expected_state"],
            "expected_failure_codes": spec["expected_failures"],
            "expected_manifest_present": spec["state"] != "unsigned",
            "how_generated": spec["how"],
            "why_it_matters": spec["why"],
        })

    if not verify_only:
        MANIFEST_PATH.write_text(json.dumps({
            "_comment": "Golden C2PA fixture inventory for markproof M2 (Art. 50 media "
                        "verification). Generated by generate.py -- do not hand-edit.",
            "_provenance": "All media are Tippel's own production, synthesised "
                           "programmatically by generate.py. No third-party asset is "
                           "present in this directory.",
            "generator": "tests/fixtures/media/generate.py",
            "c2pa_python": _pkg_version(),
            "c2pa_rs_sdk": c2pa.sdk_version(),
            "signing": {
                "warning": "TEST MATERIAL ONLY. This CA is self-signed, is in no trust "
                           "store, and must never be trusted outside these tests.",
                "algorithm": "ES256 (ECDSA P-256 / SHA-256)",
                "timestamp_authority": None,
                "trust_anchor_pem": TEST_ROOT_CA_PEM,
                "hint": "Inject trust_anchor_pem via c2pa.Settings "
                        "{'verify': {'verify_trust': true}, 'trust': {'trust_anchors': ...}} "
                        "to reach validation state 'Trusted'; without it correctly signed "
                        "fixtures validate as 'Valid' with failure "
                        "'signingCredential.untrusted'.",
            },
            "source_type_vocabulary": {
                "compliant": DST_TRAINED,
                "near_miss": DST_ALGORITHMIC,
                "capture": DST_CAPTURE,
                "composite": DST_COMPOSITE,
            },
            "files": records,
        }, indent=2, sort_keys=False) + "\n")

    return failures


def _pkg_version() -> str:
    try:
        import importlib.metadata as md
        return md.version("c2pa-python")
    except Exception:
        return "unknown"


def _regen_certs() -> None:
    """Reprint the test CA + signer. Only needed if the chain ever expires.

    Kept as a function rather than a live code path so a normal run does not
    depend on `cryptography` and the committed PEMs stay byte-stable (an ECDSA
    self-signature is randomised, so regenerating changes the constants).
    """
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    nb = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    na = datetime.datetime(2036, 1, 1, tzinfo=datetime.UTC)
    root_key = ec.derive_private_key(
        0x5F1D2C3B4A5968778695A4B3C2D1E0F00F1E2D3C4B5A69788796A5B4C3D2E1F0, ec.SECP256R1())
    ee_key = ec.derive_private_key(
        0x1A2B3C4D5E6F708192A3B4C5D6E7F8091A2B3C4D5E6F708192A3B4C5D6E7F809, ec.SECP256R1())

    def name(cn: str) -> x509.Name:
        return x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "markproof test fixtures"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "NOT FOR PRODUCTION"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ])

    def key_usage(*, cert_sign: bool) -> x509.KeyUsage:
        return x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=cert_sign,
            crl_sign=cert_sign, encipher_only=False, decipher_only=False)

    root_name = name("markproof test root CA")
    root = (x509.CertificateBuilder()
            .subject_name(root_name).issuer_name(root_name)
            .public_key(root_key.public_key())
            .serial_number(0x4D41524B50524F4F4600000001)
            .not_valid_before(nb).not_valid_after(na)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(key_usage(cert_sign=True), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()),
                           critical=False)
            .sign(root_key, hashes.SHA256()))
    ee = (x509.CertificateBuilder()
          .subject_name(name("markproof test signer")).issuer_name(root_name)
          .public_key(ee_key.public_key())
          .serial_number(0x4D41524B50524F4F4600000002)
          .not_valid_before(nb).not_valid_after(na)
          .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
          .add_extension(key_usage(cert_sign=False), critical=True)
          # The C2PA cert profile requires an EKU on the claim signer and
          # forbids anyExtendedKeyUsage; emailProtection is the interoperable
          # choice, documentSigning the semantically correct one.
          .add_extension(x509.ExtendedKeyUsage([
              ExtendedKeyUsageOID.EMAIL_PROTECTION,
              x509.ObjectIdentifier("1.3.6.1.5.5.7.3.36"),  # id-kp-documentSigning
          ]), critical=False)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ee_key.public_key()),
                         critical=False)
          .add_extension(
              x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
              critical=False)
          .sign(root_key, hashes.SHA256()))
    print((ee.public_bytes(serialization.Encoding.PEM)
           + root.public_bytes(serialization.Encoding.PEM)).decode())
    print(ee_key.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption()).decode())


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="re-create every fixture, including signed ones (changes their bytes)")
    ap.add_argument("--verify", action="store_true",
                    help="verify existing fixtures only; write nothing")
    ap.add_argument("--regenerate-test-certs", action="store_true",
                    help="print a fresh test CA + signer chain (needs `cryptography`)")
    args = ap.parse_args(argv)

    if args.regenerate_test_certs:
        _regen_certs()
        return 0

    print(f"markproof media fixtures  (c2pa-python {_pkg_version()}, "
          f"c2pa-rs {c2pa.sdk_version()})")
    failures = generate(force=args.force, verify_only=args.verify)
    if failures:
        print(f"\n{failures} fixture(s) did not match their declared state.")
        return 1
    print("\nAll fixtures match their declared state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
