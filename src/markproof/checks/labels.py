# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""Label presence checks (Art. 50(3) and 50(4)).

Deepfake and emotion-recognition disclosure labels, matched against configurable
lists in ``patterns/deepfake-labels.yaml`` and ``patterns/emotion-labels.yaml``,
each entry carrying its Guidelines reference.

v1 checks *presence*, not prominence. Whether a label is sufficiently
conspicuous is not decidable deterministically, so these rules carry severity
``warn`` and attach the evidence instead of pretending to a verdict.
"""

# TODO(M5): label list loader, presence matching over media and UI evidence.
