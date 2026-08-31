#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Generate the golden SynthID-Text fixture matrix for markproof M3.

Why this script exists
----------------------
markproof's text-marking check (``src/markproof/checks/synthid.py``) has to
answer a question that no competing tool answers against a *deployed* endpoint:
does the text this endpoint returns carry a SynthID text watermark, as EU AI
Act Art. 50(2) requires of machine-readable marking?

The detection statistic is the **mean g-value**. Google's
``SynthIDTextWatermarkLogitsProcessor.compute_g_values()`` derives it from token
ids alone -- no language model is loaded, only a tokenizer to turn text into
ids. Unwatermarked text scores ~0.50 (a fair coin over the g-bits);
watermarked text scores ~0.75-0.80.

The interesting part is what sits *between* those two numbers. A text that
scores 0.61 is not evidence of anything, and a compliance tool that rounds it
to a verdict is lying to its user. So the matrix below deliberately contains
texts engineered to land in the middle, and texts that are too short for the
statistic to mean anything at all. Those are the fixtures that matter: they
force the check to answer "uncertain" and "skipped" instead of guessing.

The four states
---------------
=================  ==================================  ==================
state              construction                        expected outcome
=================  ==================================  ==================
watermarked        tournament over 16 candidates at     watermarked
                   every position -> mean-g ~0.78
unwatermarked      tokens drawn uniformly (plus one     not_watermarked
                   hand-written English paragraph)
                   -> mean-g ~0.50
weak-signal        tournament at only ~42% of the       uncertain
                   positions -> mean-g ~0.60-0.64
too-short          below the statistical floor; one     skipped
                   of them is genuinely watermarked
                   and must STILL be skipped
=================  ==================================  ==================

Honesty note
------------
Except for ``unwatermarked-prose``, the texts are **synthetic token
sequences**, not meaningful prose. They read like word salad because they are
word salad. That is correct for this purpose and not a shortcut: the g-value
is a function of token ids and of nothing else -- not of grammar, not of
meaning, not of topic. Generating fluent watermarked text would require
running a real watermarked language model, which would make these fixtures
non-reproducible, slow, and dependent on a gated model download, while
changing the measured statistic not at all. See README.md.

Determinism
-----------
Every file here is byte-exact reproducible. The token pools are derived from a
pinned tokenizer revision and sorted by token id; all sampling uses
``random.Random`` with per-fixture integer seeds; candidate selection breaks
ties by lowest candidate index and never touches a float. Run the script twice
and compare SHA-256 -- ``--selftest`` does exactly that for you.

Usage
-----
    python generate.py              # (re)generate every fixture + MANIFEST.json
    python generate.py --verify     # verify what is on disk, write nothing
    python generate.py --selftest   # regenerate into a temp dir, diff hashes
    python generate.py --sweep      # reprint the calibration table (many seeds)

Requires the dev venv (``transformers``, ``torch``). The gpt2 tokenizer is
downloaded once from the Hugging Face hub (~2.8 MB, no access token needed)
and cached in ``~/.cache/huggingface``.
"""

# This is an operator-facing CLI generator, not shipped library code: printing
# the per-fixture verification table to stdout is the entire point of running it.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import torch
import transformers
from transformers import AutoTokenizer, SynthIDTextWatermarkLogitsProcessor

HERE = Path(__file__).resolve().parent
MANIFEST_NAME = "MANIFEST.json"

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
# gpt2 is chosen because it is ungated (no HF token, no licence click-through),
# tiny (2.8 MB of tokenizer files -- no model weights are ever fetched), quick to
# load (~7 s cold, ~4 s warm, and most of that is importing transformers), and
# byte-level BPE, which makes the decode -> encode
# round-trip verifiable rather than hopeful. bert-base-uncased was rejected: it
# lower-cases and strips, so `text` would not round-trip back to `token_ids`,
# and the fixtures would silently measure a different sequence than they claim.
#
# The revision is pinned. Without it, a re-upload of the repo could change the
# vocabulary under us and every measured mean-g in MANIFEST.json would drift.
TOKENIZER_ID = "gpt2"
TOKENIZER_REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"

# ---------------------------------------------------------------------------
# Watermark configuration -- ONE config for the whole matrix
# ---------------------------------------------------------------------------
# Every fixture is generated and verified against exactly this config, and it is
# repeated verbatim inside each fixture file and once in MANIFEST.json. g-values
# are meaningless across configs: change ngram_len, the keys, the table size or
# the table seed and every number in this directory becomes wrong.
#
# The keys are the public example keys from the transformers documentation.
# They are TEST KEYS. In a real deployment the watermarking keys are the secret
# that makes the mark unforgeable; committing them here is safe only because
# nothing in this repository ever marks real output with them.
WATERMARK_CONFIG: dict[str, Any] = {
    "ngram_len": 5,
    "keys": [654, 400, 836, 123, 340, 443, 597, 160, 57],
    "sampling_table_size": 65536,
    "sampling_table_seed": 0,
    "context_history_size": 1024,
}
DEPTH = len(WATERMARK_CONFIG["keys"])
NGRAM_LEN: int = WATERMARK_CONFIG["ngram_len"]

# ---------------------------------------------------------------------------
# Statistical floor and the bands the fixtures are verified against
# ---------------------------------------------------------------------------
# Each n-gram contributes DEPTH independent g-bits, so the mean-g of an
# unwatermarked text of N n-grams has standard deviation
#
#     sigma(N) = 0.5 / sqrt(DEPTH * N) = 0.167 / sqrt(N)
#
# For the lower decision threshold (0.56) to sit at least 3 sigma above 0.50 we
# need N >= 100 n-grams, i.e. >= 104 tokens. MIN_TOKENS is that floor rounded
# to 100; below it the check must SKIP, because the statistic cannot separate
# "clean" from "marked" no matter where the threshold is put.
#
# ``--sweep`` measures this rather than asserting it. Over 16 seeds per cell,
# unwatermarked text of 40 tokens reaches 0.540 and weakly marked text of 40
# tokens reaches 0.698 -- the two distributions have nearly met, and 0.698 would
# be reported as "watermarked" by any threshold at 0.70. At 100 tokens and above
# the same three populations stay cleanly separated on every seed, which is
# exactly the property --sweep asserts before it exits.
MIN_TOKENS = 100

# Thresholds recommended to the check author, derived from the measurements
# printed by this script (see README.md, "Calibration").
RECOMMENDED_LOWER_THRESHOLD = 0.56  # <= this  -> not_watermarked
RECOMMENDED_UPPER_THRESHOLD = 0.70  # >= this  -> watermarked
#                                     between -> uncertain

# Acceptance bands used to VERIFY generated fixtures. Deliberately tighter than
# the recommended thresholds: a fixture that only just clears the threshold it
# is supposed to demonstrate is a fixture that will flake the day somebody
# nudges the threshold by 0.01.
STATE_BANDS: dict[str, tuple[float, float]] = {
    "watermarked": (0.72, 1.00),
    "unwatermarked": (0.44, 0.55),
    "weak-signal": (0.585, 0.660),
}
EXPECTED_OUTCOME: dict[str, str] = {
    "watermarked": "watermarked",
    "unwatermarked": "not_watermarked",
    "weak-signal": "uncertain",
    "too-short": "skipped",
}

# ---------------------------------------------------------------------------
# Fixture specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Spec:
    """One fixture. ``seed``, ``length``, ``candidates`` and ``marked_fraction``
    fully determine the token sequence -- nothing else is consulted."""

    fixture_id: str
    state: str
    length: int
    candidates: int  # tournament size; 1 == no tournament, plain sampling
    marked_fraction: float  # share of positions that run the tournament
    seed: int
    why_it_matters: str
    prose: str | None = None  # hand-written text instead of sampled tokens

    @property
    def filename(self) -> str:
        return f"{self.fixture_id}.json"


# A paragraph written by hand for this repository. It is here so the matrix
# contains at least one *real* sentence-shaped negative: proof that ordinary
# human writing scores ~0.5 and is not flagged. No third-party text is used.
HUMAN_PROSE = (
    "markproof runs a deterministic check against a live endpoint and records what it "
    "actually observed, rather than asking the operator to describe their own system. The "
    "disclosure check reads the response body, the media check reads the provenance manifest, "
    "and the text check reads the token stream. None of the three trusts a self declaration, "
    "because a self declaration is precisely the thing an audit is supposed to test. This "
    "paragraph was written by a human being at a keyboard on an ordinary afternoon, so its "
    "token sequence carries no watermark of any kind and the measured statistic should sit "
    "close to one half. If a detector claims otherwise about this text, the detector is wrong "
    "and the threshold behind it needs to be moved before anybody relies on the result in a "
    "compliance report or a regulatory filing of any sort whatsoever."
)

SPECS: tuple[Spec, ...] = (
    # -- watermarked ---------------------------------------------------------
    Spec(
        "watermarked-120",
        "watermarked",
        120,
        16,
        1.0,
        1101,
        "Shortest fully marked text still above MIN_TOKENS. Proves the check fires at the "
        "floor and does not need a wall of text to reach a verdict.",
    ),
    Spec(
        "watermarked-240",
        "watermarked",
        240,
        16,
        1.0,
        1102,
        "The ordinary marked case: a typical chatbot answer length, unambiguous signal.",
    ),
    Spec(
        "watermarked-480",
        "watermarked",
        480,
        16,
        1.0,
        1103,
        "Long marked text. mean-g must stay ~0.78 and not drift with length -- a check that "
        "accumulates instead of averaging would show length dependence here.",
    ),
    # -- unwatermarked -------------------------------------------------------
    Spec(
        "unwatermarked-120",
        "unwatermarked",
        120,
        1,
        0.0,
        2101,
        "Clean text at the length floor, where the statistic is noisiest. The false-positive "
        "case that decides whether MIN_TOKENS is set honestly.",
    ),
    Spec(
        "unwatermarked-240",
        "unwatermarked",
        240,
        1,
        0.0,
        2102,
        "The ordinary clean case. Must never be reported as marked.",
    ),
    Spec(
        "unwatermarked-480",
        "unwatermarked",
        480,
        1,
        0.0,
        2103,
        "Long clean text; mean-g converges tightly on 0.50.",
    ),
    Spec(
        "unwatermarked-prose",
        "unwatermarked",
        0,  # length comes from the tokenizer
        1,
        0.0,
        0,
        "Real, human-written English rather than sampled tokens. The others prove the "
        "statistic behaves; this one proves it behaves on text a person would actually send.",
        prose=HUMAN_PROSE,
    ),
    # -- weak-signal ---------------------------------------------------------
    Spec(
        "weak-signal-160",
        "weak-signal",
        160,
        16,
        0.40,
        3101,
        "Partly marked text, e.g. a marked draft a human rewrote. THE case that must come "
        "back uncertain: any verdict here is a guess dressed as evidence.",
    ),
    Spec(
        "weak-signal-240",
        "weak-signal",
        240,
        16,
        0.42,
        3102,
        "Same mechanism at ordinary length. Sits near the middle of the uncertain band, so "
        "it stays uncertain even if either threshold moves by 0.03.",
    ),
    Spec(
        "weak-signal-400",
        "weak-signal",
        400,
        16,
        0.42,
        3103,
        "Long partly-marked text. Length removes the excuse that the ambiguity is small-sample "
        "noise: the signal really is intermediate, and more tokens will not resolve it.",
    ),
    # -- too-short -----------------------------------------------------------
    Spec(
        "too-short-3",
        "too-short",
        3,
        1,
        0.0,
        4101,
        "Fewer tokens than ngram_len, so compute_g_values() raises RuntimeError. The check "
        "must skip on token count BEFORE calling into transformers, not catch an exception.",
    ),
    Spec(
        "too-short-5",
        "too-short",
        5,
        1,
        0.0,
        4102,
        "Exactly ngram_len: one single n-gram. A number is produced (~0.33) and it is pure "
        "noise. Computable is not the same as meaningful.",
    ),
    Spec(
        "too-short-24",
        "too-short",
        24,
        1,
        0.0,
        4103,
        "A one-sentence reply. Plausible endpoint output, still far below the floor.",
    ),
    Spec(
        "too-short-64-marked",
        "too-short",
        64,
        16,
        1.0,
        4104,
        "The sharp one: genuinely watermarked, mean-g well above the upper threshold, but "
        "under MIN_TOKENS. It must STILL be skipped. Length gating has to run before the "
        "statistic, or the tool reports a verdict it cannot defend -- and the same gate that "
        "protects against false positives has to cost us this true positive.",
    ),
)


# ---------------------------------------------------------------------------
# Token pools
# ---------------------------------------------------------------------------
# Restricting the vocabulary is not cosmetic, it is what makes `text` and
# `token_ids` the same object. GPT-2 pre-tokenises on the regex ` ?\p{L}+`, so a
# token that is a space followed by ASCII letters is its own pre-token: joining
# such tokens and re-encoding returns the identical id sequence. Mix in
# punctuation, digits or byte fragments and adjacent tokens start merging on
# re-encode, at which point the fixture would measure a sequence different from
# the one it advertises. Every generated fixture is round-trip asserted anyway.
_CONTINUATION_RE = re.compile(r"^Ġ[a-z]{3,10}$")  # Ġ == GPT-2 "Ġ" (space)
_HEAD_RE = re.compile(r"^[A-Z][a-z]{2,9}$")


def build_pools(tokenizer: Any) -> tuple[list[int], list[int]]:
    """Return (head_ids, continuation_ids), both sorted by token id."""
    vocab = tokenizer.get_vocab()
    heads = sorted(tid for tok, tid in vocab.items() if _HEAD_RE.match(tok))
    conts = sorted(tid for tok, tid in vocab.items() if _CONTINUATION_RE.match(tok))
    if len(heads) < 100 or len(conts) < 1000:
        raise SystemExit(
            f"token pools too small (heads={len(heads)}, continuations={len(conts)}); "
            "the tokenizer revision is probably not the pinned one"
        )
    return heads, conts


# ---------------------------------------------------------------------------
# g-values
# ---------------------------------------------------------------------------


def make_processor() -> SynthIDTextWatermarkLogitsProcessor:
    return SynthIDTextWatermarkLogitsProcessor(
        ngram_len=WATERMARK_CONFIG["ngram_len"],
        keys=list(WATERMARK_CONFIG["keys"]),
        sampling_table_size=WATERMARK_CONFIG["sampling_table_size"],
        sampling_table_seed=WATERMARK_CONFIG["sampling_table_seed"],
        context_history_size=WATERMARK_CONFIG["context_history_size"],
        device=torch.device("cpu"),
    )


def _batch(rows: list[list[int]]) -> torch.LongTensor:
    """Token-id batch as a LongTensor.

    ``compute_g_values`` is annotated with the legacy ``torch.LongTensor``
    alias, which ``torch.tensor(..., dtype=torch.long)`` does not satisfy
    statically even though it is exactly the right runtime type. The cast is
    the whole reason this helper exists.
    """
    return cast("torch.LongTensor", torch.tensor(rows, dtype=torch.long))


def mean_g(processor: SynthIDTextWatermarkLogitsProcessor, ids: list[int]) -> float | None:
    """Mean g-value over all n-grams and all depths, or None if uncomputable."""
    if len(ids) < NGRAM_LEN:
        return None
    g = processor.compute_g_values(input_ids=_batch([ids]))
    # g is 0/1 longs: sum exactly in integers, divide once. No float accumulation,
    # so the value is bit-identical on every run and every machine.
    total = int(g.sum().item())
    count = g.shape[1] * g.shape[2]
    return total / count


def _tournament_pick(
    processor: SynthIDTextWatermarkLogitsProcessor,
    context: list[int],
    candidates: list[int],
) -> int:
    """Pick the candidate whose n-gram carries the most g-bits.

    This is what the SynthID sampler does at generation time, minus the language
    model: the model proposes candidates, the watermark picks among them. Here
    the "model" proposes uniformly, which is why the text is nonsense and why the
    g-statistic is nevertheless exactly right.

    Ties go to the lowest candidate index -- torch.argmax makes no such promise.
    """
    batch = _batch([[*context, cand] for cand in candidates])
    sums = processor.compute_g_values(input_ids=batch).sum(dim=(1, 2)).tolist()
    best = 0
    for i in range(1, len(candidates)):
        if sums[i] > sums[best]:
            best = i
    return candidates[best]


def build_sequence(
    processor: SynthIDTextWatermarkLogitsProcessor,
    heads: list[int],
    conts: list[int],
    spec: Spec,
) -> list[int]:
    """Build one token sequence exactly as ``spec`` describes it."""
    # S311: Mersenne Twister is exactly what is wanted here. Nothing about these
    # fixtures is a secret; reproducibility is the requirement, and a CSPRNG
    # would make the committed files impossible to regenerate.
    rng = random.Random(spec.seed)  # noqa: S311
    ids: list[int] = [heads[rng.randrange(len(heads))]]
    while len(ids) < spec.length:
        pos = len(ids)
        # Drawn unconditionally so the RNG stream depends only on position,
        # never on the branch taken.
        roll = rng.random()
        can_mark = pos >= NGRAM_LEN - 1 and spec.candidates > 1
        if can_mark and roll < spec.marked_fraction:
            candidates = [conts[rng.randrange(len(conts))] for _ in range(spec.candidates)]
            ids.append(_tournament_pick(processor, ids[pos - (NGRAM_LEN - 1) : pos], candidates))
        else:
            ids.append(conts[rng.randrange(len(conts))])
    return ids


# ---------------------------------------------------------------------------
# Fixture assembly
# ---------------------------------------------------------------------------


def how_generated(spec: Spec) -> str:
    if spec.prose is not None:
        return (
            "Hand-written English paragraph (Tippel's own text), tokenised with "
            f"{TOKENIZER_ID}@{TOKENIZER_REVISION[:7]}. No watermarking of any kind."
        )
    if spec.candidates <= 1:
        return (
            f"{spec.length} tokens drawn uniformly at random (random.Random(seed={spec.seed})) "
            "from the round-trip-safe GPT-2 word pool. No tournament, so every g-bit is a fair "
            "coin."
        )
    if spec.marked_fraction >= 1.0:
        return (
            f"{spec.length} tokens; at every position from index {NGRAM_LEN - 1} on, "
            f"{spec.candidates} candidates are drawn and the one whose n-gram carries the most "
            f"g-bits wins (random.Random(seed={spec.seed})). This reproduces SynthID tournament "
            "sampling with a uniform proposal distribution."
        )
    return (
        f"{spec.length} tokens; the {spec.candidates}-candidate tournament runs at a randomly "
        f"chosen {spec.marked_fraction:.0%} of positions and the remaining positions are drawn "
        f"uniformly (random.Random(seed={spec.seed})). Models text that is only partly machine "
        "generated, which is what lands the mean-g between the thresholds."
    )


def make_fixture(
    processor: SynthIDTextWatermarkLogitsProcessor,
    tokenizer: Any,
    heads: list[int],
    conts: list[int],
    spec: Spec,
) -> dict[str, Any]:
    if spec.prose is not None:
        token_ids = list(tokenizer(spec.prose)["input_ids"])
        text = spec.prose
    else:
        token_ids = build_sequence(processor, heads, conts, spec)
        text = tokenizer.decode(token_ids)

    # Hard requirement: the check will tokenise `text`, so `text` must produce
    # exactly `token_ids`. If it does not, the fixture measures one sequence and
    # the check measures another, and every number below is a lie.
    reencoded = list(tokenizer(text)["input_ids"])
    if reencoded != token_ids:
        raise SystemExit(
            f"{spec.fixture_id}: text does not round-trip to token_ids "
            f"({len(token_ids)} -> {len(reencoded)} tokens)"
        )

    measured = mean_g(processor, token_ids)
    return {
        "id": spec.fixture_id,
        "state": spec.state,
        "text": text,
        "token_ids": token_ids,
        "token_count": len(token_ids),
        "measured_mean_g": None if measured is None else round(measured, 6),
        "expected_outcome": EXPECTED_OUTCOME[spec.state],
        "watermark_config": dict(WATERMARK_CONFIG),
        "tokenizer": TOKENIZER_ID,
        "tokenizer_revision": TOKENIZER_REVISION,
        "min_tokens": MIN_TOKENS,
        "how_generated": how_generated(spec),
        "why_it_matters": spec.why_it_matters,
    }


def check_fixture(fixture: dict[str, Any]) -> list[str]:
    """Return a list of problems; empty means the fixture is honest."""
    problems: list[str] = []
    state = fixture["state"]
    count = fixture["token_count"]
    measured = fixture["measured_mean_g"]

    if fixture["expected_outcome"] != EXPECTED_OUTCOME[state]:
        problems.append("expected_outcome does not match state")
    if fixture["watermark_config"] != WATERMARK_CONFIG:
        problems.append("watermark_config differs from the single shared config")

    if state == "too-short":
        if count >= MIN_TOKENS:
            problems.append(f"token_count {count} is not below MIN_TOKENS {MIN_TOKENS}")
    else:
        if count < MIN_TOKENS:
            problems.append(f"token_count {count} is below MIN_TOKENS {MIN_TOKENS}")
        low, high = STATE_BANDS[state]
        if measured is None:
            problems.append("measured_mean_g is null")
        elif not low <= measured <= high:
            problems.append(f"mean-g {measured:.4f} outside {state} band [{low}, {high}]")
    return problems


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def dump_json(payload: dict[str, Any] | list[Any]) -> str:
    """One canonical encoder for every file: stable key order is guaranteed by
    insertion order, ASCII-only output removes any locale or encoding drift, and
    the trailing newline keeps POSIX tools happy."""
    return json.dumps(payload, indent=2, ensure_ascii=True) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate(out_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID, revision=TOKENIZER_REVISION)
    processor = make_processor()
    heads, conts = build_pools(tokenizer)

    out_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    failures: list[str] = []

    for spec in SPECS:
        fixture = make_fixture(processor, tokenizer, heads, conts, spec)
        problems = check_fixture(fixture)
        if problems:
            failures.extend(f"{spec.fixture_id}: {p}" for p in problems)

        body = dump_json(fixture)
        (out_dir / spec.filename).write_text(body, encoding="utf-8")
        fixtures.append(fixture)
        entries.append(
            {
                "filename": spec.filename,
                "id": fixture["id"],
                "state": fixture["state"],
                "token_count": fixture["token_count"],
                "measured_mean_g": fixture["measured_mean_g"],
                "expected_outcome": fixture["expected_outcome"],
                "sha256": sha256_text(body),
                "size_bytes": len(body.encode("utf-8")),
                "generation": {
                    "source": "hand-written prose" if spec.prose else "sampled tokens",
                    "tournament_candidates": spec.candidates,
                    "marked_fraction": spec.marked_fraction,
                    "seed": spec.seed,
                },
                "how_generated": fixture["how_generated"],
                "why_it_matters": fixture["why_it_matters"],
            }
        )

    manifest = build_manifest(entries, processor, len(heads), len(conts))
    (out_dir / MANIFEST_NAME).write_text(dump_json(manifest), encoding="utf-8")
    return fixtures, failures


def build_manifest(
    entries: list[dict[str, Any]],
    processor: SynthIDTextWatermarkLogitsProcessor,
    n_heads: int,
    n_conts: int,
) -> dict[str, Any]:
    by_state: dict[str, list[float]] = {}
    for entry in entries:
        if entry["measured_mean_g"] is not None:
            by_state.setdefault(entry["state"], []).append(entry["measured_mean_g"])

    return {
        "_comment": (
            "Golden SynthID-Text fixture inventory for markproof M3 (Art. 50 text marking). "
            "Generated by generate.py -- do not hand-edit."
        ),
        "_provenance": (
            "All texts are Tippel's own production: sampled token sequences built by "
            "generate.py, plus one hand-written English paragraph. No third-party text and no "
            "model output from any provider is present in this directory."
        ),
        "generator": "tests/fixtures/text/generate.py",
        "transformers": transformers.__version__,
        "torch": torch.__version__,
        "tokenizer": {
            "id": TOKENIZER_ID,
            "revision": TOKENIZER_REVISION,
            "class": "GPT2Tokenizer",
            "vocab_size": 50257,
            "gated": False,
            "cache_size_kb": 2804,
            "note": (
                "Tokenizer files only (vocab.json, merges.txt, tokenizer.json); no model "
                "weights are downloaded. Detection needs token ids, not a language model."
            ),
            "pool_sizes": {"heads": n_heads, "continuations": n_conts},
        },
        "watermark_config": dict(WATERMARK_CONFIG),
        "watermark_config_note": (
            "Identical in every fixture file. g-values are only comparable within one config: "
            "changing ngram_len, keys, sampling_table_size or sampling_table_seed invalidates "
            "every measured_mean_g below. The keys are the public example keys from the "
            "transformers docs and are TEST KEYS -- never mark production output with them."
        ),
        "statistic": {
            "definition": (
                "mean over all n-grams and all "
                f"{DEPTH} key depths of compute_g_values(token_ids); no language model involved"
            ),
            "expected_mean_g_watermarked_theory": round(processor.expected_mean_g_value(50257), 6),
            "expected_mean_g_unwatermarked_theory": 0.5,
            "sigma_formula": "0.5 / sqrt(depth * n_ngrams) = 0.167 / sqrt(n_ngrams)",
        },
        "thresholds": {
            "min_tokens": MIN_TOKENS,
            "recommended_lower": RECOMMENDED_LOWER_THRESHOLD,
            "recommended_upper": RECOMMENDED_UPPER_THRESHOLD,
            "decision_rule": (
                f"token_count < {MIN_TOKENS} -> skipped; "
                f"mean_g <= {RECOMMENDED_LOWER_THRESHOLD} -> not_watermarked; "
                f"mean_g >= {RECOMMENDED_UPPER_THRESHOLD} -> watermarked; "
                "otherwise -> uncertain"
            ),
            "rationale": (
                "Reproduce every number below with `python generate.py --sweep` (16 seeds per "
                f"cell). min_tokens: sigma(100 n-grams) = 0.0167, so {RECOMMENDED_LOWER_THRESHOLD}"
                " sits 3.6 sigma above 0.5 for clean text at the floor; at 40 tokens the clean "
                "and the weakly-marked populations nearly touch (0.540 vs 0.565) and weakly "
                "marked text reaches 0.698, which any 0.70 threshold would call watermarked. "
                f"lower: at >= {MIN_TOKENS} tokens the unwatermarked maximum was 0.519. "
                "upper: at the same lengths the watermarked minimum was 0.764, so 0.70 keeps "
                "~0.06 of headroom while leaving the uncertain band wide enough that partly "
                "marked text (measured 0.586-0.657) lands inside it instead of on a verdict."
            ),
            "verification_bands": {
                state: list(band) for state, band in sorted(STATE_BANDS.items())
            },
        },
        "measured_by_state": {
            state: {
                "count": len(values),
                "min": min(values),
                "max": max(values),
            }
            for state, values in sorted(by_state.items())
        },
        "files": entries,
    }


# ---------------------------------------------------------------------------
# Verification of what is on disk
# ---------------------------------------------------------------------------


def verify(directory: Path) -> list[str]:
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID, revision=TOKENIZER_REVISION)
    processor = make_processor()
    failures: list[str] = []

    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.exists():
        return [f"{manifest_path} is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["watermark_config"] != WATERMARK_CONFIG:
        failures.append("MANIFEST.json watermark_config differs from generate.py")

    listed = {entry["filename"] for entry in manifest["files"]}
    on_disk = {p.name for p in directory.glob("*.json")} - {MANIFEST_NAME}
    for extra in sorted(on_disk - listed):
        failures.append(f"{extra}: on disk but not in MANIFEST.json")

    for entry in manifest["files"]:
        name = entry["filename"]
        path = directory / name
        if not path.exists():
            failures.append(f"{name}: listed in MANIFEST.json but missing")
            continue
        body = path.read_text(encoding="utf-8")
        if sha256_text(body) != entry["sha256"]:
            failures.append(f"{name}: sha256 does not match MANIFEST.json")

        fixture = json.loads(body)
        failures.extend(f"{name}: {p}" for p in check_fixture(fixture))

        if list(tokenizer(fixture["text"])["input_ids"]) != fixture["token_ids"]:
            failures.append(f"{name}: text no longer tokenises to token_ids")
        if len(fixture["token_ids"]) != fixture["token_count"]:
            failures.append(f"{name}: token_count does not match len(token_ids)")

        measured = mean_g(processor, fixture["token_ids"])
        claimed = fixture["measured_mean_g"]
        if measured is None:
            if claimed is not None:
                failures.append(
                    f"{name}: claims a mean-g but the sequence is shorter than ngram_len"
                )
        elif claimed is None or round(measured, 6) != claimed:
            # Stored at 6 decimals; that is ~5 orders of magnitude below the
            # narrowest band, so the comparison is exact where it matters.
            failures.append(f"{name}: recomputed mean-g {measured!r} != stored {claimed!r}")
        if entry["measured_mean_g"] != claimed:
            failures.append(f"{name}: MANIFEST.json mean-g disagrees with the fixture file")
    return failures


def selftest() -> list[str]:
    """Regenerate into a temp dir and prove the output is byte-identical."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp) / "text"
        generate(tmp_dir)
        for path in sorted(HERE.glob("*.json")):
            other = tmp_dir / path.name
            if not other.exists():
                failures.append(f"{path.name}: not produced by the second run")
                continue
            a, b = sha256_text(path.read_text()), sha256_text(other.read_text())
            status = "ok " if a == b else "DIFF"
            print(f"  {status} {path.name:26s} {a[:16]}")
            if a != b:
                failures.append(f"{path.name}: second run differs ({a} != {b})")
    return failures


# ---------------------------------------------------------------------------
# Calibration sweep
# ---------------------------------------------------------------------------

SWEEP_LENGTHS = (40, 64, 80, 100, 120, 160, 240, 400, 480)
SWEEP_SEEDS = 16
SWEEP_SEED_BASE = 9000


def sweep() -> list[str]:
    """Reprint the calibration table the README and the thresholds rest on.

    The committed fixtures are single draws; this sweeps many seeds per length
    so the claim "unwatermarked never reaches 0.56 above MIN_TOKENS" is a
    measurement rather than an assertion. Writes nothing.
    """
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_ID, revision=TOKENIZER_REVISION)
    processor = make_processor()
    heads, conts = build_pools(tokenizer)

    def band(length: int, candidates: int, fraction: float) -> tuple[float, float]:
        values: list[float] = []
        for offset in range(SWEEP_SEEDS):
            spec = Spec(
                "sweep", "watermarked", length, candidates, fraction, SWEEP_SEED_BASE + offset, ""
            )
            measured = mean_g(processor, build_sequence(processor, heads, conts, spec))
            if measured is None:  # every SWEEP_LENGTHS entry is well above ngram_len
                raise SystemExit(f"sweep length {length} is shorter than ngram_len {NGRAM_LEN}")
            values.append(measured)
        return min(values), max(values)

    print(f"mean-g over {SWEEP_SEEDS} seeds per cell (min .. max)")
    print(f"{'tokens':>6s}   {'unwatermarked':^16s}   {'weak-signal':^16s}   {'watermarked':^16s}")
    print("-" * 66)
    failures: list[str] = []
    for length in SWEEP_LENGTHS:
        clean = band(length, 1, 0.0)
        weak = band(length, 16, 0.42)
        marked = band(length, 16, 1.0)
        print(
            f"{length:6d}   {clean[0]:.3f} .. {clean[1]:.3f}   "
            f"{weak[0]:.3f} .. {weak[1]:.3f}   {marked[0]:.3f} .. {marked[1]:.3f}"
        )
        if length < MIN_TOKENS:
            continue
        # Above the floor the recommended thresholds must separate all three.
        if clean[1] > RECOMMENDED_LOWER_THRESHOLD:
            failures.append(f"length {length}: unwatermarked reached {clean[1]:.3f}")
        if marked[0] < RECOMMENDED_UPPER_THRESHOLD:
            failures.append(f"length {length}: watermarked fell to {marked[0]:.3f}")
        if not (weak[0] > RECOMMENDED_LOWER_THRESHOLD and weak[1] < RECOMMENDED_UPPER_THRESHOLD):
            failures.append(f"length {length}: weak-signal escaped the uncertain band {weak}")
    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_table(fixtures: list[dict[str, Any]]) -> None:
    print(f"{'fixture':24s} {'state':14s} {'tokens':>6s} {'mean-g':>8s}  expected")
    print("-" * 74)
    for fixture in fixtures:
        measured = fixture["measured_mean_g"]
        shown = "  n/a  " if measured is None else f"{measured:7.4f}"
        print(
            f"{fixture['id']:24s} {fixture['state']:14s} "
            f"{fixture['token_count']:6d} {shown:>8s}  {fixture['expected_outcome']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--verify", action="store_true", help="verify on-disk fixtures, write nothing"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="regenerate into a temp dir and diff hashes"
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="reprint the calibration table behind MIN_TOKENS and the thresholds",
    )
    args = parser.parse_args(argv)

    if args.verify:
        failures = verify(HERE)
    elif args.selftest:
        failures = selftest()
    elif args.sweep:
        failures = sweep()
    else:
        fixtures, failures = generate(HERE)
        print_table(fixtures)
        print()
        failures += verify(HERE)

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
