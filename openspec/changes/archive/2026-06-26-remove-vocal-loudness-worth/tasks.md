## 1. Render Behavior

- [x] 1.1 Remove the `--vocal-loudness-worth` / `-vlw` option from the render CLI and command plumbing.
- [x] 1.2 Remove `VOCAL_LOUDNESS_WORTH`, `_get_vocal_loudness_worth`, and all vocal-loudness-worth arguments from render process APIs.
- [x] 1.3 Stop wrapping instrumental, DJ instrumental, and a cappella renders in `adjust_master_limiter_threshold`.
- [x] 1.4 Remove the now-unused master limiter threshold adjustment helper and related limiter range constant if no other code uses them.

## 2. Project Metadata Cleanup

- [x] 2.1 Remove Reaper project-note metadata parsing from `ExtendedProject`.
- [x] 2.2 Remove imports and tests that only support project-note metadata parsing.

## 3. Version and Specifications

- [x] 3.1 Bump the package version from `2.0.0` to `3.0.0`.
- [x] 3.2 Update render specifications by applying the removed vocal-loudness compensation requirement.

## 4. Tests and Verification

- [x] 4.1 Run `uv sync --all-extras` before checks in the fresh environment.
- [x] 4.2 Update render and CLI snapshots so help output, mocked calls, metadata lookups, and limiter parameter writes reflect the new behavior.
- [x] 4.3 Add or adjust focused tests to verify reduced versions still render with the expected muting behavior and no automatic limiter adjustment.
- [x] 4.4 Run repo-wide static checks with `uv run check --fix`.
- [x] 4.5 Run focused render tests with `uv run pytest tests/commands/render tests/test_cli.py tests/utils/test_project.py`.
