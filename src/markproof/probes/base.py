# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Probe protocol and the Evidence container.

Every probe implements ``collect() -> Evidence``. Evidence is a serialisable
record of what the endpoint returned, with a SHA-256 digest per stored artefact
so that findings can reference immutable inputs.
"""

# TODO(M1): Probe protocol (collect), Evidence / Artifact models,
#           artefact storage layout under artifacts/.
# TODO(M5): endpoint errors (timeout, TLS, 401/429/5xx) become the finding
#           MPF-X-001 "endpoint unreachable" — a FAIL, never a crash.
