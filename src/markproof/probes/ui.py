# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""UI probe (optional extra ``[ui]``) — Playwright against a rendered chat widget.

Loads the page, locates ``chat_selector``, and records the *visible* text
(``inner_text``, not raw HTML — a disclosure hidden by CSS is not a disclosure)
together with a screenshot as evidence.

Optional by design: the extra pulls browser binaries at run time, so the default
path must never require it.
"""

# TODO(M5): page load, selector wait, inner_text + screenshot evidence.
# TODO(M5): fail loudly with an install hint when the [ui] extra is missing.
