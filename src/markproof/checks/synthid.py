# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""SynthID text watermark verification (Art. 50(2)) — the second half of the lane.

Answers one question about a deployed endpoint: does the text it returns still
carry the watermark its operator says it applies? No other tool in this field
asks that of a live endpoint.

**This is a self-conformance test, not detection in the wild.** It needs the
operator's own watermark configuration — the keys and n-gram length used at
generation time. That dependency is the honest shape of the problem: without the
config, any verdict would be a guess, and a compliance report must not rest on
one. It also means markproof cannot be turned into a universal AI-text detector,
which is a boundary worth keeping.

Mechanism, in one paragraph. SynthID biases token sampling toward tokens with a
high pseudorandom "g value" derived from the preceding n-gram and the operator's
keys. Recomputing those g values over the returned token sequence and averaging
them yields a score: chance sits near 0.50, a watermarked sequence near 0.75.
Computing g values needs the tokenizer and the config, never the language model
itself — verification is therefore cheap and offline.

Scores are evidence, not verdicts. Between the two thresholds the answer is
``uncertain``, and the rule decides what that means. Reporting a number the
tool is not confident about as a pass would be exactly the guessing this
project exists to avoid.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field

from markproof.optional import OptionalDependencyError
from markproof.rules.schema import SynthIdDetectCheck

if TYPE_CHECKING:  # pragma: no cover - import cost only matters at runtime
    pass

#: Above this, a score is no longer explainable as chance. Derived from the
#: calibration sweep, where clean text at 100+ tokens never exceeded 0.519.
_CHANCE_CEILING = 0.55

__all__ = [
    "SynthIdOutcome",
    "SynthIdResult",
    "WatermarkConfig",
    "detect_watermark",
    "load_watermark_config",
]


class SynthIdUnavailableError(OptionalDependencyError):
    """The optional detection stack is not installed.

    ``transformers`` and ``torch`` are a heavy extra, so a rulepack asking for
    text marking on a build without them is a configuration error with a fix,
    not a silent skip.
    """


class WatermarkConfig(BaseModel):
    """The generation-side parameters, as the operator hands them over.

    Mirrors ``SynthIDTextWatermarkingConfig``. In production these keys are a
    secret: anyone holding them can both verify and forge the mark.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ngram_len: int = Field(ge=2)
    keys: list[int] = Field(min_length=1)
    sampling_table_size: int = Field(default=65536, ge=2)
    sampling_table_seed: int = 0
    context_history_size: int = Field(default=1024, ge=1)
    tokenizer: str = Field(min_length=1)
    """Tokenizer name or path. Must be the one used at generation time — g
    values are computed over token ids, so a different tokenizer scores a
    different sequence and the result would be meaningless."""


class SynthIdOutcome(StrEnum):
    """What the detector concluded."""

    WATERMARKED = "watermarked"
    NOT_WATERMARKED = "not_watermarked"
    UNCERTAIN = "uncertain"
    TOO_SHORT = "too_short"
    UNSUPPORTED = "unsupported"


class SynthIdResult(BaseModel):
    """Score plus everything needed to re-derive it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: SynthIdOutcome
    score: float | None = None
    token_count: int = 0
    detector: str = "mean-g"
    thresholds: tuple[float, float] | None = None
    detail: str | None = None

    @property
    def passed(self) -> bool:
        return self.outcome is SynthIdOutcome.WATERMARKED


def load_watermark_config(path: Path) -> WatermarkConfig:
    """Load the operator's watermark configuration.

    Raises:
        ValueError: if the file is missing or does not describe a full config.
            A partial config would silently score against the wrong parameters.
    """
    if not path.is_file():
        raise ValueError(
            f"watermark config not found: {path} — text marking cannot be "
            "verified without the parameters used at generation time"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: not valid JSON — {exc}") from exc
    return WatermarkConfig.model_validate(raw)


def _load_tokenizer(name: str) -> Any:
    """Load the tokenizer, raising a config-shaped error if unavailable."""
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - exercised by the extras test
        raise SynthIdUnavailableError(
            "text marking needs the optional extra: pip install 'markproof[synthid]'"
        ) from exc

    try:
        return AutoTokenizer.from_pretrained(name)
    except Exception as exc:
        raise ValueError(
            f"could not load tokenizer {name!r}: {exc}. It must be the tokenizer "
            "used at generation time, available locally or from the model hub."
        ) from exc


def _mean_g_score(token_ids: list[int], config: WatermarkConfig) -> float:
    """Average g value over a token sequence.

    Pure given the same inputs: the processor derives its sampling table from
    the configured seed, so two runs on the same ids produce the same score.
    """
    try:
        import torch
        from transformers import SynthIDTextWatermarkLogitsProcessor
    except ImportError as exc:  # pragma: no cover - exercised by the extras test
        raise SynthIdUnavailableError(
            "text marking needs the optional extra: pip install 'markproof[synthid]'"
        ) from exc

    processor = SynthIDTextWatermarkLogitsProcessor(
        ngram_len=config.ngram_len,
        keys=config.keys,
        sampling_table_size=config.sampling_table_size,
        sampling_table_seed=config.sampling_table_seed,
        context_history_size=config.context_history_size,
        device=torch.device("cpu"),
    )
    # cast: torch.tensor returns Tensor, and the processor is annotated for
    # LongTensor. dtype=long makes them the same object at runtime.
    ids = cast("Any", torch.tensor([token_ids], dtype=torch.long))
    g_values = processor.compute_g_values(input_ids=ids)
    return float(g_values.float().mean().item())


def detect_watermark(
    text: str,
    check: SynthIdDetectCheck,
    config: WatermarkConfig,
    *,
    token_ids: list[int] | None = None,
) -> SynthIdResult:
    """Decide whether a piece of text carries the operator's watermark.

    Args:
        text: The endpoint's response.
        check: The rule's detection parameters.
        config: The operator's generation-side watermark configuration.
        token_ids: Pre-tokenised ids, which skip loading a tokenizer. Used by
            tests and by callers that already hold the ids.

    Returns:
        A result carrying the score, the thresholds it was judged against, and
        the token count — everything a reader needs to check the reasoning.
    """
    if check.detector == "bayesian":
        return SynthIdResult(
            outcome=SynthIdOutcome.UNSUPPORTED,
            detector=check.detector,
            detail=(
                "the bayesian detector needs a trained BayesianDetectorModel from "
                "the operator; this build implements the mean-g detector, which "
                "needs only the watermark config"
            ),
        )

    if token_ids is None:
        tokenizer = _load_tokenizer(config.tokenizer)
        token_ids = list(tokenizer(text, add_special_tokens=False)["input_ids"])

    count = len(token_ids)
    bounds = (check.thresholds.not_watermarked_below, check.thresholds.watermarked_at)

    if count < check.min_tokens:
        return SynthIdResult(
            outcome=SynthIdOutcome.TOO_SHORT,
            token_count=count,
            detector=check.detector,
            thresholds=bounds,
            detail=(
                f"{count} tokens is below the {check.min_tokens} needed for a "
                "meaningful score — the detector's confidence grows with length, "
                "and a short sample would be noise dressed as a verdict"
            ),
        )

    # A sequence shorter than the n-gram window yields no g values at all.
    if count <= config.ngram_len:
        return SynthIdResult(
            outcome=SynthIdOutcome.TOO_SHORT,
            token_count=count,
            detector=check.detector,
            thresholds=bounds,
            detail=f"sequence shorter than the {config.ngram_len}-gram window",
        )

    score = _mean_g_score(token_ids, config)

    if score >= check.thresholds.watermarked_at:
        outcome = SynthIdOutcome.WATERMARKED
        detail = None
    elif score < check.thresholds.not_watermarked_below:
        outcome = SynthIdOutcome.NOT_WATERMARKED
        # Only call it chance level when it actually is. A score can sit below a
        # deliberately strict lower bound and still be far above 0.5, and a
        # report that misdescribes its own evidence is worse than a terse one.
        near_chance = score < _CHANCE_CEILING
        detail = (
            f"mean g value {score:.4f} is at chance level — the text carries no "
            "detectable watermark under this configuration"
            if near_chance
            else (
                f"mean g value {score:.4f} is elevated but below the configured "
                f"lower bound of {check.thresholds.not_watermarked_below}"
            )
        )
    else:
        outcome = SynthIdOutcome.UNCERTAIN
        detail = (
            f"mean g value {score:.4f} falls between {bounds[0]} and {bounds[1]} — "
            "elevated but not conclusive; a longer sample would settle it"
        )

    return SynthIdResult(
        outcome=outcome,
        score=round(score, 6),
        token_count=count,
        detector=check.detector,
        thresholds=bounds,
        detail=detail,
    )
