# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""HTML-templated PDF renderer (extra ``[pdf-html]``) — weasyprint.

Prettier output for people who want it, never in the critical path (Auflage A2).
weasyprint needs Pango, cairo and GdkPixbuf, which pip cannot install; the docs
name the ``apt`` line explicitly.

When the system libraries are missing this renderer must abort with an
explanatory message, not crash — the portability test asserts exactly that.
"""

# TODO(M4): HTML/CSS template + render(report, path).
# TODO(M4): graceful, explanatory failure when Pango/cairo are unavailable.
