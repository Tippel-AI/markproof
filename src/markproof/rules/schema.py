# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Rulepack schema (pydantic), exportable as JSON Schema.

A rulepack carries its id, version, ``license: CC-BY-4.0``, a mandatory
``attribution:`` line and a ``source:`` list; each rule carries id, title, the
Article it serves, a ``guideline_ref`` clause/margin number, ``applies_to``,
the ``check`` block and a severity.

The ``attribution`` field is required, not optional: it is how the CC-BY
obligation on the derived Commission material is discharged (Auflage H1). Rules
paraphrase the sources and cite clause numbers — no verbatim paragraphs in YAML.
"""

# TODO(M1): Rulepack / Rule / Check models, mandatory attribution validator,
#           `markproof rules schema` JSON Schema export.
