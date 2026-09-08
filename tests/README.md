# Tests

Most tests should use the smallest double that makes the behavior observable.
`unittest.mock` and pytest's `monkeypatch` remain the default for simple
substitution, environment/configuration changes, filesystem or process
simulation, and open-ended collaborator graphs.

## Using wrapture

Use wrapture when the test needs to keep project-owned, already-imported Python
code real while asserting call order, nesting, or an action that must not occur
after a failure. Bindings are function-scoped context managers: the context
that applies a binding owns its removal. Do not share applied bindings, mix
lifecycle owners for one target, or enable the wrapture pytest plugin without a
separate evaluation.

The focused examples are:

- `tests/commands/test_upload.py` observes the real upload workflow while
  stubbing only its `ClientSession` boundary.
- `tests/commands/render/test_render.py` uses phased behavior to inject the
  third render failure in the existing mixed-error scenario.

Do not bind `reapy`, `curl_cffi`, builtin or extension types, dynamically
provided attributes, subprocesses, filesystem operations, environment values,
or work running in threads/executors. Keep using an explicit fake or the
existing mocking tools at those boundaries.

Strict `wrapture.mock(Spec)` doubles check their declared surface and method
signatures. An unconfigured method returns `None`; attempting to use that
result cannot produce a fabricated `MagicMock` call chain.

## Alpha dependency maintenance

wrapture is a test-only dependency pinned exactly to `1.0.0a21`. Do not widen
the constraint or accept a pre-release upgrade indirectly. For an intentional
upgrade:

1. Update the exact pin and `uv.lock`, then run `uv sync --all-extras`.
2. Verify the installed version imports on Python 3.12, 3.13, and 3.14.
3. Run `uv run pytest tests/commands/test_upload.py` and
   `uv run pytest tests/commands/render/test_render.py`.
4. Run `uv run check --fix` and `uv run pytest`.

The render comparison did not remove enough of the dynamic REAPER fixture to
justify a wider migration. Keep it as the canonical phased-failure example;
evaluate any shared fixture rewrite in a separate change.

Rollback is simple: remove the test extra, lockfile entries, focused pilots,
and this guidance. Application modules must not import or configure wrapture.
