## Tests

- Before running checks or tests in a fresh or uncertain environment, run
  `uv sync --all-extras`.
- Run static checks with `uv run check --fix`.
  - Static checks should run repo-wide, regardless of which files changed.
- Run focused tests `uv run pytest` for the code you changed.
  - Run the full test suite when changes are cross-cutting.

### Style

- This repo generally prefers snapshot tests for CLI output, rendered tables,
  mock call sequences, and similar structured results.
- When extending an area that already uses snapshots, prefer updating an
  existing snapshot test over adding a new one-off assertion test.
- Use targeted non-snapshot assertions for one narrow contract where a snapshot
  would capture incidental detail.
  - Examples: one ordering rule, one field, one warning, one invariant, or one
    presence/absence check.
- Avoid mixing styles unnecessarily within the same behavior.
  - Keep the main coverage in the style already used nearby, and add
    supplemental assertions only when they add signal.
