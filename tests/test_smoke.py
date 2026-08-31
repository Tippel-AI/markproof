# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Smoke test for the M0 skeleton.

There is no behaviour to test yet. This keeps `pytest` from exiting with
"no tests collected" on the 3.11/3.12/3.13 matrix, so the CI badge means
something from day one.
"""

import markproof


def test_package_is_importable() -> None:
    assert markproof.__doc__ is not None


# TODO(M1): replace with real unit tests — checks in isolation, DE/EN Unicode
#           cases for the disclosure patterns, evaluator determinism.
# TODO(M4): signature roundtrip and the RFC 8785 test vectors.
