# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Text watermark detection (Art. 50(2)) — the second half of the unique lane.

Optional extra ``[synthid]`` (transformers + torch, CPU is enough). Detection
needs the operator's own watermark config, which is exactly why markproof is a
self-conformance test: "prove that YOUR marking survives end to end", not a
detector for other people's AI text.

Two detector paths:

``mean-g`` (default)
    Weighted mean score. Needs the watermark config only — no trained detector
    model, which is what makes it the low-prerequisite default.
``bayesian``
    Requires the operator's trained detector model (``detector_model:``).
    Missing path is a hard config error, never a silent fallback to ``mean-g``.

Three-state output, exposed rather than hidden: ``watermarked`` /
``not_watermarked`` / ``uncertain``, with the thresholds configurable per rule
(``watermarked_at``, ``not_watermarked_below``). ``uncertain`` maps to FAIL by
default (``on_uncertain``) because conformance has to be demonstrable, not
merely plausible. Score, thresholds and sample statistics always land in the
evidence so an auditor can recompute the decision.

Trademark hygiene (Auflage A3): SynthID is a Google DeepMind trademark, named
here descriptively only. No component of markproof carries that name.
"""

# TODO(M3): watermark config loader (SynthIDTextWatermarkingConfig format),
#           mean-g and bayesian paths, three-state mapping, FP/FN notes in docs/synthid.md.
# TODO(M3): determinism — fixed seed, torch.use_deterministic_algorithms(True),
#           golden tests over frozen endpoint responses.
