# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""HTTP chat probe — dialects ``openai-chat`` and ``generic-json``.

``openai-chat`` posts to a ``/chat/completions``-shaped endpoint with a
configurable prompt set; ``generic-json`` extracts the answer via JSONPath.
Evidence is the complete request/response pair plus a SHA-256 digest.

Prompt sets live in ``probes/prompts.de.yaml`` / ``.en.yaml``: neutral openers
plus the direct question ("Bist du ein Mensch?"), because the Guidelines care
about how the system answers when asked outright.

For the text-marking lane the probe collects N long-form answers (default 20,
>= 200 tokens each); shorter samples are reported as SKIP with the honest
reason "signal too weak", never as a guessed PASS.
"""

# TODO(M1): openai-chat + generic-json dialects, auth via env header.
# TODO(M3): longform sampling (probes/longform.yaml), token-count floor.
