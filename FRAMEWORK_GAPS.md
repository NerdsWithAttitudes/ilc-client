# Framework Gaps

## Active candidates

1. Route return-state should preserve declared Python type
- classification: `framework-gap`
- status: open
- rationale: method signatures can declare concrete return types, but callers
  may still receive generic JSON-like values at runtime. The framework should
  decode to the declared type consistently.
- impact in this package: evaluator result parsing stays in package code
  (`src/ilc/example_ops.py`) instead of relying on framework-native typed decode.
