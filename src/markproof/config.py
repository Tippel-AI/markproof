# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Pydantic model of the target config (``markproof.yaml``).

Mirrors ``examples/markproof.yaml``: a ``target`` with one or more probes
(``http-chat`` | ``ui`` | ``media``), a ``text_marking`` block (method,
watermark config path, detector), the selected ``rulepack``, and the ``report``
block (signing key source, output formats).

Secrets are never inlined: auth tokens and the SynthID watermark config are
referenced by environment variable or file path and resolved at run time.
"""

# TODO(M1): TargetConfig / ProbeConfig / TextMarkingConfig / ReportConfig models.
# TODO(M1): loader on top of ruamel.yaml with precise validation errors
#           (unknown check type => hard config error, never a silent SKIP).
