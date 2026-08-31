# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Media probe — fetch generated assets and preserve the bytes untouched.

Calls the image/media endpoint (``images/generations`` dialect or a generic
download of a returned URL) and stores raw bytes plus Content-Type. Nothing is
re-encoded: any transformation would destroy the C2PA hash bindings that
``markproof.checks.c2pa_verify`` is about to check.

v1 formats: PNG, JPEG, MP4, WAV. Everything else yields SKIP with a reason.
"""

# TODO(M2): images/generations dialect + generic URL download,
#           byte-exact storage, Content-Type vs. sniffed-format mismatch as evidence.
