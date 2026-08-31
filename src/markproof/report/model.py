# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Report data model — one structure, several renderers.

Holds the markproof version, the rulepack id and version, the target name, run
metadata (start time, git sha, CI system), the findings list with evidence
(probe, artefact path, SHA-256, detector score and thresholds where relevant),
the PASS/FAIL/WARN/SKIP summary, and the signature block.

The signature block records the canonicaliser and its exact version
(``"canonicalizer": "rfc8785==0.1.4"``) so the signature stays reproducible
years later. JSON, Markdown summary and both PDF renderers all read from this
model — never from each other.
"""

# TODO(M4): Report / Finding / Evidence / Signature models with SHA-256 artefact refs.
