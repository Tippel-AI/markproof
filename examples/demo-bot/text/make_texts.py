# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the demo-bot's chat answer texts. Development tool, never a runtime.

The demo-bot serves the ``.txt`` files next to this script; it does not mark
anything at request time. Marking per request would mean loading a tokenizer
and running a search inside the request path, and the search is a *choice among
wordings* — the same request would keep returning the same bytes only as long
as nothing about the lattice, the tokenizer or the torch build moved. Committed
files make that guarantee unconditional, exactly as ``media/make_fixtures.py``
does for the signed images (README §Determinism).

Two renderings come out of every lattice in ``lattice.py``:

``marked/``   word choices picked to raise the SynthID-style g-values of the
              resulting token sequence. Served in ``DEMO_MODE=pass`` and
              ``DEMO_MODE=wrongtype``.
``plain/``    word choices picked by a rule that never looks at a g-value.
              Served in ``DEMO_MODE=nomark``.

Both carry the same disclosure sentences, the same length and the same
register. That is the point of the pair: the only difference between them is
which synonym was taken at each slot, so a detector that separates them is
reading the marking and nothing else.

HOW THE MARKING IS BUILT
------------------------
There is no language model here, and none is needed. A SynthID-style text
watermark is a property of the *token sequence*, not of the model that produced
it: ``compute_g_values`` maps each n-gram to a 0/1 value per key, and marked
text is text whose token sequence happens to score high. A real generator
reaches that with tournament sampling over the model's own candidate
continuations. This script reaches it by searching a hand-written lattice of
interchangeable phrasings — same objective, a much smaller candidate space, and
no model weights in the repository.

The search is a beam over the lattice, scored by *excess*

    excess = sum(g) - 0.5 * count(g)

rather than by the mean. Excess is length-neutral: a token that carries no
signal contributes zero in expectation, so a path is never rewarded merely for
being longer than its rivals, and paths that consumed the same slots stay
comparable even when their alternatives tokenised to different lengths.

WHY THE CONFIG CARRIES ONLY THREE KEYS
--------------------------------------
Depth is the one config parameter this demo cannot choose freely. A tournament
sampler with the whole vocabulary to draw from reaches
``expected_mean_g_value`` ≈ 0.75 at *any* depth, because every layer gets its
own two-way contest. A search over a hand-written lattice does not: it has to
find one phrasing that scores well on all layers at once, and the achievable
mean-g falls off as ``1/sqrt(depth * tokens per choice)``. Measured on this
lattice, German lands at 0.76 with three keys, 0.72 with four and 0.64 with
nine — so three is the largest depth at which the fixtures still sit in the
band real watermarked text occupies. A real deployment, marking with a model
instead of a word list, uses many more.

Three layers over four hundred n-grams is twelve hundred Bernoulli draws, a
null standard deviation of 0.014 and a separation of roughly eighteen sigma
between the marked and plain fixtures. Detection strength is not what the low
depth costs; it costs headroom in the search.

Needs the dev environment, not the demo-bot's own requirements.txt:

    pip install "transformers>=5" "torch>=2" && python examples/demo-bot/text/make_texts.py

CPU is enough; nothing here allocates a model.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoTokenizer
from transformers.generation.logits_process import SynthIDTextWatermarkLogitsProcessor

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lattice import (
    DE_DISCLOSURE,
    DE_IDENTITY,
    DE_NOTICE,
    EN_DISCLOSURE,
    EN_IDENTITY,
    EN_NOTICE,
    Lattice,
    Pick,
    lattices,
)

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE.parent / "watermark_config.json"

#: Beam width. Wide enough that a locally poor choice which sets up a strong
#: context survives to be judged on the result; narrow enough to finish in
#: seconds. The beam is deterministic — ties break on insertion order.
BEAM_WIDTH = 96

#: A rendering below the floor is not usable as a *marked* fixture, and one
#: above the ceiling is not usable as an *unmarked* one. Between the two lies
#: the band a detector reports as uncertain; neither fixture may sit there.
#:
#: The ceiling is the shipped rule's ``not_watermarked_below`` exactly
#: (MPF-T-001 in ``art50-eu-2026.07``), so the generator refuses to emit a
#: control sample that rule would not call unwatermarked. The floor is
#: deliberately stricter than that rule's ``watermarked_at`` of 0.70: it sits
#: at ``expected_mean_g_value`` (0.74999… for a 50k vocabulary), the strength
#: real tournament sampling converges on. A fixture that only just cleared
#: 0.70 would let a threshold drift upward unnoticed.
MARKED_FLOOR = 0.74
PLAIN_CEILING = 0.56

#: Art. 50(2) detection needs enough n-grams to be worth a verdict. The issue
#: asks for 250; the lattices comfortably clear it, and the check is an
#: assertion rather than a hope.
MIN_TOKENS = 250

#: Watermark-blind slot selection for the plain rendering: step 5 through a
#: pool, which is coprime with every pool size used, so the walk visits every
#: alternative before repeating and never correlates with a g-value.
PLAIN_STRIDE = 5
PLAIN_OFFSET = 2


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class WatermarkConfig:
    """The operator's marking parameters — the file handed to markproof."""

    tokenizer: str
    ngram_len: int
    keys: list[int]
    sampling_table_size: int
    sampling_table_seed: int
    context_history_size: int

    @classmethod
    def load(cls, path: Path) -> WatermarkConfig:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            tokenizer=raw["tokenizer"],
            ngram_len=raw["ngram_len"],
            keys=list(raw["keys"]),
            sampling_table_size=raw["sampling_table_size"],
            sampling_table_seed=raw["sampling_table_seed"],
            context_history_size=raw["context_history_size"],
        )

    def processor(self) -> SynthIDTextWatermarkLogitsProcessor:
        return SynthIDTextWatermarkLogitsProcessor(
            ngram_len=self.ngram_len,
            keys=self.keys,
            sampling_table_size=self.sampling_table_size,
            sampling_table_seed=self.sampling_table_seed,
            context_history_size=self.context_history_size,
            device=torch.device("cpu"),
        )


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def g_values(processor: SynthIDTextWatermarkLogitsProcessor, tokens: list[int]) -> torch.Tensor:
    """All g-values of a token sequence: ``(len - ngram_len + 1, depth)``."""
    if len(tokens) < processor.ngram_len:
        return torch.zeros((0, len(processor.keys)))
    ids = torch.tensor([tokens], dtype=torch.long)
    return processor.compute_g_values(ids)[0].float()


def mean_g(processor: SynthIDTextWatermarkLogitsProcessor, tokens: list[int]) -> float:
    """The mean-g statistic markproof's default detector path computes."""
    values = g_values(processor, tokens)
    return float(values.mean()) if values.numel() else 0.0


def masked_mean_g(
    processor: SynthIDTextWatermarkLogitsProcessor, tokens: list[int]
) -> tuple[float, int, int]:
    """Mean-g over n-grams whose context has not been seen before.

    The reference detector drops repeated contexts: a marker that has already
    committed to a context does not get a second vote from it. Reported
    alongside the raw mean so that a check adopting either convention can be
    read against these fixtures. Returns ``(mean, kept, total)``.
    """
    if len(tokens) < processor.ngram_len:
        return 0.0, 0, 0
    ids = torch.tensor([tokens], dtype=torch.long)
    values = processor.compute_g_values(ids)[0].float()
    keep = processor.compute_context_repetition_mask(ids)[0].bool()
    kept = values[keep]
    total = int(keep.numel())
    if not kept.numel():
        return 0.0, 0, total
    return float(kept.mean()), int(keep.sum()), total


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def strip_lead(text: str) -> str:
    """Drop a unit's leading separator — only the document's first unit needs it."""
    return text.lstrip(" \n")


@dataclass(frozen=True)
class Step:
    """One decision in the flattened lattice; a literal is a decision of one.

    ``group`` is set for the positions of a ``Pick``, which share a pool and
    must not repeat an entry. ``opens_group`` marks the first of them, where
    the used-set starts over.
    """

    options: tuple[str, ...]
    group: int | None = None
    opens_group: bool = False


def flatten(lattice: Lattice) -> list[Step]:
    """Lattice to a flat decision stream, expanding every ``Pick`` in place.

    The document's very first step loses its leading separator: units carry
    one so they can be concatenated, and the opening of a text has nothing to
    be separated from.
    """
    steps: list[Step] = []
    group = 0
    for unit in lattice:
        if isinstance(unit, Pick):
            group += 1
            for position in range(unit.count):
                separator = unit.lead if position == 0 else unit.sep
                steps.append(
                    Step(
                        options=tuple(separator + item for item in unit.pool),
                        group=group,
                        opens_group=position == 0,
                    )
                )
        elif isinstance(unit, str):
            steps.append(Step(options=(unit,)))
        else:
            steps.append(Step(options=tuple(unit)))
    if steps:
        head = steps[0]
        steps[0] = Step(
            options=tuple(strip_lead(option) for option in head.options),
            group=head.group,
            opens_group=head.opens_group,
        )
    return steps


@dataclass(frozen=True)
class Candidate:
    """One partial rendering: the text so far, its tokens and its g-score."""

    text: str
    tokens: tuple[int, ...]
    g_sum: float
    g_count: int
    used: frozenset[int]

    @property
    def excess(self) -> float:
        """Signal above the null expectation. Length-neutral, unlike the mean."""
        return self.g_sum - 0.5 * self.g_count

    @property
    def mean(self) -> float:
        return self.g_sum / self.g_count if self.g_count else 0.0


def render_marked(
    lattice: Lattice,
    tokenizer: object,
    processor: SynthIDTextWatermarkLogitsProcessor,
) -> str:
    """Beam-search the lattice for the rendering with the strongest marking.

    Extensions are scored in batches: every (path, option) pair whose option
    tokenises to the same length shares one ``compute_g_values`` call, since
    each of them contributes the same number of new n-grams over a context
    window of the same width. Without that the search spends its whole runtime
    in per-pair tensor construction.
    """
    window = processor.ngram_len - 1
    encoded: dict[str, list[int]] = {}
    beam = [Candidate(text="", tokens=(), g_sum=0.0, g_count=0, used=frozenset())]

    for step in flatten(lattice):
        for option in step.options:
            if option not in encoded:
                encoded[option] = tokenizer(option)["input_ids"]

        # Every extension this step allows, as (path, option, scoring row).
        # Only the last ngram_len - 1 tokens of a path can influence a new
        # n-gram, so that window is the whole context the score needs.
        rows: list[tuple[int, int, list[int]]] = []
        used_for: list[frozenset[int]] = []
        for path_index, path in enumerate(beam):
            used = frozenset() if step.opens_group else path.used
            used_for.append(used)
            tail = path.tokens[-window:] if len(path.tokens) >= window else path.tokens
            context = list(tail)
            for option_index, option in enumerate(step.options):
                if step.group is not None and option_index in used:
                    continue
                rows.append((path_index, option_index, context + encoded[option]))

        # Rows of equal width share one call: same context width, same option
        # length, so they yield the same number of new n-grams each.
        by_width: dict[int, list[tuple[int, int, list[int]]]] = {}
        for row in rows:
            by_width.setdefault(len(row[2]), []).append(row)

        grown: list[Candidate] = []
        for width, group_rows in by_width.items():
            if width < processor.ngram_len:
                sums = [0.0] * len(group_rows)
                count = 0
            else:
                batch = torch.tensor([row[2] for row in group_rows], dtype=torch.long)
                values = processor.compute_g_values(batch).float()
                sums = values.sum(dim=(1, 2)).tolist()
                count = int(values.shape[1] * values.shape[2])
            for (path_index, option_index, _), total in zip(group_rows, sums, strict=True):
                path = beam[path_index]
                option = step.options[option_index]
                grown.append(
                    Candidate(
                        text=path.text + option,
                        tokens=path.tokens + tuple(encoded[option]),
                        g_sum=path.g_sum + total,
                        g_count=path.g_count + count,
                        used=(
                            used_for[path_index] | {option_index}
                            if step.group is not None
                            else frozenset()
                        ),
                    )
                )

        # Sorting on excess alone would let a one-token length difference break
        # a tie; the text keeps the ordering total, stable and reproducible.
        grown.sort(key=lambda candidate: (-candidate.excess, candidate.text))
        beam = grown[:BEAM_WIDTH]

    # Excess drove the search because it is length-neutral; mean-g decides the
    # winner because mean-g is the statistic the detector reports.
    return max(beam, key=lambda path: (path.mean, path.text)).text


def render_plain(lattice: Lattice) -> str:
    """Render without ever consulting a g-value.

    The selection walks each pool with a fixed stride, so the text varies from
    slot to slot and stays reproducible, while nothing about the choice can
    correlate with the watermark. Inside a ``Pick`` the walk skips entries it
    has already spent, which keeps the no-repeat rule the marked rendering
    obeys. This is the control sample.
    """
    out: list[str] = []
    slot = 0
    used: set[int] = set()
    for step in flatten(lattice):
        if len(step.options) == 1:
            out.append(step.options[0])
            continue
        if step.opens_group:
            used = set()
        index = (slot * PLAIN_STRIDE + PLAIN_OFFSET) % len(step.options)
        while step.group is not None and index in used:
            index = (index + 1) % len(step.options)
        if step.group is not None:
            used.add(index)
        out.append(step.options[index])
        slot += 1
    return "".join(out)


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
#: Sentences that must survive every rendering, per language. The M1 rules read
#: these; a regeneration that dropped one would leave a bot that still answers
#: but no longer discloses, and that has to fail here rather than in CI.
ANCHORS: dict[str, tuple[str, ...]] = {
    "de": (DE_DISCLOSURE, DE_IDENTITY, DE_NOTICE),
    "en": (EN_DISCLOSURE, EN_IDENTITY, EN_NOTICE),
}


def expected_anchors(name: str) -> tuple[str, ...]:
    """Which anchors a given variant must contain."""
    lang, kind, turn = name.split("-")
    required = []
    if turn == "first":
        required.append(ANCHORS[lang][0])
    if kind == "identity":
        required.append(ANCHORS[lang][1])
    if turn == "later":
        required.append(ANCHORS[lang][2])
    return tuple(required)


def check_tokenisation(tokenizer: object, text: str, tokens: list[int]) -> None:
    """The finished string must tokenise to what the search scored.

    The search adds one unit at a time; BPE merges across a unit boundary would
    make the sequence it scored a different sequence from the one the detector
    will see. Every unit carries a leading separator precisely to prevent that,
    and this is where the claim is tested instead of trusted.
    """
    if tokenizer(text)["input_ids"] != tokens:
        raise ValueError(
            "incremental tokenisation drifted from the finished text — a lattice "
            "unit is missing its leading separator"
        )


def check_text(name: str, variant: str, text: str, tokens: list[int]) -> None:
    """Everything the served file has to satisfy before it is written."""
    for anchor in expected_anchors(name):
        if anchor not in text:
            raise ValueError(f"{variant}/{name}: anchor sentence missing: {anchor!r}")
    if len(tokens) < MIN_TOKENS:
        raise ValueError(f"{variant}/{name}: {len(tokens)} tokens, need at least {MIN_TOKENS}")
    if unicodedata.normalize("NFC", text) != text:
        raise ValueError(f"{variant}/{name}: text is not NFC-normalised")
    if text != text.strip():
        raise ValueError(f"{variant}/{name}: text has leading or trailing whitespace")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    config = WatermarkConfig.load(CONFIG_PATH)
    tokenizer = AutoTokenizer.from_pretrained(config.tokenizer)
    processor = config.processor()

    print(f"tokenizer            {config.tokenizer} (vocab {tokenizer.vocab_size})")
    print(f"ngram_len            {config.ngram_len}")
    print(f"depth (keys)         {len(config.keys)}")
    print(f"expected mean-g      {processor.expected_mean_g_value(tokenizer.vocab_size):.4f}")
    print(f"marked floor         {MARKED_FLOOR:.2f}   plain ceiling {PLAIN_CEILING:.2f}")
    print()

    records: list[dict[str, object]] = []
    header = (
        f"{'variant':<20} {'kind':<7} {'tokens':>7} {'mean-g':>8} {'masked':>8} {'ctx kept':>10}"
    )
    print(header)
    print("-" * len(header))

    for name, lattice in lattices().items():
        for variant, renderer in (
            ("marked", lambda lat: render_marked(lat, tokenizer, processor)),
            ("plain", render_plain),
        ):
            text = renderer(lattice)
            tokens = tokenizer(text)["input_ids"]
            check_tokenisation(tokenizer, text, tokens)
            check_text(name, variant, text, tokens)

            raw = mean_g(processor, tokens)
            masked, kept, total = masked_mean_g(processor, tokens)
            if variant == "marked" and raw < MARKED_FLOOR:
                raise ValueError(f"marked/{name}: mean-g {raw:.4f} below floor {MARKED_FLOOR}")
            if variant == "plain" and raw > PLAIN_CEILING:
                raise ValueError(f"plain/{name}: mean-g {raw:.4f} above ceiling {PLAIN_CEILING}")

            path = HERE / variant / f"{name}.txt"
            path.write_text(text + "\n", encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            print(
                f"{name:<20} {variant:<7} {len(tokens):>7} {raw:>8.4f} "
                f"{masked:>8.4f} {kept:>4}/{total:<5}"
            )
            lang, kind, turn = name.split("-")
            records.append(
                {
                    "filename": f"{variant}/{name}.txt",
                    "lang": lang,
                    "kind": kind,
                    "turn": turn,
                    "variant": variant,
                    "sha256": digest,
                    "chars": len(text),
                    "tokens": len(tokens),
                    "mean_g": round(raw, 6),
                    "mean_g_context_masked": round(masked, 6),
                    "ngrams_kept": kept,
                    "ngrams_total": total,
                }
            )

    manifest = {
        "_comment": (
            "Inventory of the demo-bot's pre-marked chat answers. Generated by "
            "make_texts.py -- do not hand-edit."
        ),
        "_provenance": (
            "All phrasings are Tippel's own production, written into lattice.py. No text "
            "is sampled from a model and none is taken from a third party."
        ),
        "generator": "examples/demo-bot/text/make_texts.py",
        "watermark_config": "examples/demo-bot/watermark_config.json",
        "tokenizer": config.tokenizer,
        "transformers": __import__("transformers").__version__,
        "torch": torch.__version__,
        "search": {
            "beam_width": BEAM_WIDTH,
            "objective": "sum(g) - 0.5 * count(g)",
            "marked_floor": MARKED_FLOOR,
            "plain_ceiling": PLAIN_CEILING,
        },
        "expected_mean_g_value": round(processor.expected_mean_g_value(tokenizer.vocab_size), 6),
        "files": records,
    }
    (HERE / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    marked = [r["mean_g"] for r in records if r["variant"] == "marked"]
    plain = [r["mean_g"] for r in records if r["variant"] == "plain"]
    print()
    print(f"marked mean-g  {min(marked):.4f} … {max(marked):.4f}")
    print(f"plain  mean-g  {min(plain):.4f} … {max(plain):.4f}")
    print(f"separation     {min(marked) - max(plain):.4f}")


if __name__ == "__main__":
    main()
