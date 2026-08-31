# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Report layer — the build artefact a DPO files away.

Output tiers, in order of portability (Auflage A2):

``json``      always produced, zero system dependencies, Ed25519-signed
``summary``   Markdown for ``$GITHUB_STEP_SUMMARY``, zero system dependencies
``pdf``       reportlab, pure Python — the portable PDF default
``pdf-html``  weasyprint, needs Pango/cairo/GdkPixbuf — never in the critical path

Only the first two are in the critical path. The signed JSON is the actual
evidence; it has to be producible on any runner, PDF or no PDF.
"""

# TODO(M4): wire the format selection from markproof.yaml `report.formats`.
