# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: curated patterns and a minimal rulepack."""

from __future__ import annotations

import pytest

from markproof.checks.disclosure import Pattern, PatternSet
from markproof.rules.schema import (
    DisclosurePatternCheck,
    Obligation,
    Position,
    ProbeKind,
    Rule,
    Rulepack,
    Severity,
    Source,
)


@pytest.fixture
def pattern_set() -> PatternSet:
    """A small curated set covering both languages and both polarities."""
    return PatternSet(
        version=1,
        description="test fixture",
        patterns=(
            Pattern(
                id="de-explicit-ki",
                lang="de",
                kind="regex",
                value=r"ich bin (?:eine? )?(?:ki|künstliche[rn]? intelligenz|chatbot)",
            ),
            Pattern(id="de-automated", lang="de", kind="substring", value="automatisiertes System"),
            Pattern(
                id="en-explicit-ai",
                lang="en",
                kind="regex",
                value=r"i(?:'m| am) an? (?:ai|artificial intelligence|chatbot)",
            ),
        ),
        negative_patterns=(
            Pattern(
                id="de-vague-assistant", lang="de", kind="substring", value="ich bin Ihr Assistent"
            ),
            Pattern(
                id="en-vague-assistant", lang="en", kind="substring", value="i am your assistant"
            ),
        ),
    )


@pytest.fixture
def disclosure_check() -> DisclosurePatternCheck:
    """Check requiring disclosure before the first user message.

    Only valid for rendered interfaces — a rulepack pairing this position with
    an ``http-chat`` probe is rejected at load time, which is why the rulepack
    fixture below uses the chat-appropriate position instead.
    """
    return DisclosurePatternCheck(
        type="disclosure-pattern",
        patterns_file="disclosure.de-en.yaml",
        position=Position.BEFORE_FIRST_USER_MESSAGE,
        min_matches=1,
    )


@pytest.fixture
def chat_check() -> DisclosurePatternCheck:
    """Check as a chat endpoint rule uses it: inspect the first response."""
    return DisclosurePatternCheck(
        type="disclosure-pattern",
        patterns_file="disclosure.de-en.yaml",
        position=Position.ANYWHERE_IN_FIRST_RESPONSE,
        min_matches=1,
    )


@pytest.fixture
def rulepack(chat_check: DisclosurePatternCheck) -> Rulepack:
    """A minimal but valid rulepack with one blocking disclosure rule."""
    return Rulepack(
        rulepack="test-pack",
        version="1.0.0",
        license="CC-BY-4.0",
        attribution=(
            "Derived from: European Commission guidelines on Article 50 transparency "
            "obligations — CC BY 4.0. Rules are paraphrased."
        ),
        source=[Source(title="Test source", date="2026-07-20", url="https://example.invalid/g")],
        rules=[
            Rule(
                id="MPF-D-001",
                title="AI disclosure before first interaction",
                article="Art. 50(1)",
                obligation=Obligation.AI_INTERACTION,
                guideline_ref="Guidelines §3.2",
                applies_to=[ProbeKind.HTTP_CHAT],
                check=chat_check,
                severity=Severity.FAIL,
            )
        ],
    )
