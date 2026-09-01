# SPDX-FileCopyrightText: 2026 Lukas Friedrich / Tippel
# SPDX-License-Identifier: Apache-2.0
"""One base class for "this build cannot do that, and here is how to install it".

markproof keeps its heavy parts optional on purpose: the default path has to work
on any runner with no system dependencies, so SynthID, the browser and both PDF
renderers arrive through extras. Each of them already raised a well-worded error
naming the extra to install.

What was missing was a way for the CLI to *catch* them as a group. It listed the
exceptions it knew about, `SynthIdUnavailableError` was not among them, and so the
README's own demo command on a base install ended in a stack trace and exit 1 —
which in this tool means "a rule failed". A stranger's first contact was a
traceback answering the compliance question with a stack frame.

Naming the shared case is what stops that recurring the next time an optional
dependency is added.
"""

from __future__ import annotations

__all__ = ["OptionalDependencyError"]


class OptionalDependencyError(RuntimeError):
    """An optional extra this build does not have is needed to answer.

    Not a rule failure and not a bug: the run could not be performed. The CLI maps
    it to exit 2 and prints the message, which is expected to name the install
    command.
    """
