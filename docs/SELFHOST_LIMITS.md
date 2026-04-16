# Selfhost Limits

This repository treats selfhost as complete for the current Norscode language surface.

## What is supported

- `la`, `sett`, `returner`
- `hvis ... da ... ellers ...`
- `hvis ... ellers hvis ... ellers ...`
- `mens`, `for`, `bryt`, `fortsett`
- assignments, compound assignments, lists, indexes, calls, and module calls

## Deliberate remaining limit

Member expressions as first-class values are still not part of the selfhost AST bridge.

That means:

- dotted names used as module/function access are supported
- arbitrary `Member` expressions that are not module paths are not lowered by selfhost yet

This is a deliberate boundary, not a parser regression.
It keeps the current selfhost pipeline aligned with the features used by the test suite.

## Practical rule

If a feature is already used by the current tests or documented core syntax, selfhost should support it.
If the feature would require a new AST/runtime model, it should be treated as a future language extension instead of a missing fix.
