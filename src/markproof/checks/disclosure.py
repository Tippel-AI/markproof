# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Disclosure check (Art. 50(1)) — does the system say it is an AI, and when?

Matches curated patterns from ``patterns/disclosure.de-en.yaml`` (regex plus
normalised substrings, Unicode-normalised, case-insensitive) against the probe
evidence, and checks the position — the disclosure has to be there before the
first user message, not somewhere further down the transcript.

Deliberately no fuzzy score: a pattern matches or it does not. Cases the
patterns cannot settle (is the wording "clear and distinguishable"?) end as WARN
with the evidence attached.

Positioning note: this lane is already occupied by notice generators and website
scanners. markproof does not *generate* disclosure text — it verifies that the
text reaches the running system.
"""

# TODO(M1): pattern loader, Unicode normalisation, position check,
#           interface-language handling (DE/EN in v1).
