# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Portable PDF renderer (extra ``[pdf]``) — reportlab, pure Python.

The default PDF path because it has zero system dependencies and therefore
works on any CI runner (Auflage A2). Imperative layout instead of HTML
templating is a deliberate trade: robustness over template beauty.

Contents: summary table, findings with their Guidelines references, rulepack
version and attribution line, signature fingerprint. Corporate-neutral,
printable, no third-party logos (Auflage A3).
"""

# TODO(M4): render(report, path) using reportlab platypus.
# TODO(M4): clear, actionable error when the [pdf] extra is not installed.
