<!--
Thanks for contributing. Two things this project cares about more than most:

  * A verdict must never claim more than was measured. If a change makes a check
    stricter or more confident, say what evidence justifies the extra confidence.
  * Documentation is part of the surface. A README that promises what the code
    does not do is a defect here, not a nit.
-->

## What changes, and why

## Does this change any verdict?

<!-- If yes: which rule, in which direction, and the golden diff that shows it.
     `pytest -m determinism` will fail until the goldens are regenerated, which is
     deliberate — a golden diff is a change in what the tool calls conformant, and
     it belongs in the review. -->

- [ ] No verdict changes
- [ ] Verdicts change, and the golden diff is in this PR

## Checks

- [ ] `pytest` passes
- [ ] `ruff check .` and `mypy` pass
- [ ] Docs updated if the change is user-visible
