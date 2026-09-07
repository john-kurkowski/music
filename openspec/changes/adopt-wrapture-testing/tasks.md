## 1. Pin the test-only evaluation dependency

- [ ] 1.1 Add `wrapture==1.0.0a21` to the `testing` optional dependency group and regenerate `uv.lock`; verify `uv sync --all-extras` resolves the exact package without adding it to `[project].dependencies`.
- [ ] 1.2 Confirm the pinned package imports under the repository's supported Python interpreters and record its installed version in the change validation notes; verify the import reports `1.0.0a21` and no application module imports `wrapture`.

## 2. Add the scoped upload pilot

- [ ] 2.1 Add small explicit response doubles local to the upload test support (status code plus JSON payload only); verify they cover the pilot without using a chained or spec-less `Mock` response.
- [ ] 2.2 Add a function-scoped wrapture timeline test for the real upload `Process` and project-owned `ClientSession` methods; stub only the initial track lookup and verify the lookup completes before upload work begins while no outbound mutation method is called for a missing track.
- [ ] 2.3 Add a function-scoped error-path timeline test that injects failure at the upload-policy request; verify the real upload workflow returns the expected failure result and never streams the file or requests transcoding after that failure.
- [ ] 2.4 Keep the existing `requests_mocks` fixture and snapshot tests unchanged except where a focused test needs a shared literal; verify the new tests pass independently with `uv run pytest tests/commands/test_upload.py` and pass twice in the same pytest invocation without patch-lifecycle leakage.

## 3. Compare the render fixture on a failure workflow

- [ ] 3.1 Add a comparison test beside `test_main_mixed_errors` that preserves its three-render failure scenario and observable CLI behavior; verify the current baseline test and comparison test both pass before considering any shared-fixture edit.
- [ ] 3.2 Build the comparison from bindings on project-owned Python render orchestration and only stable, named strict collaborators; verify no binding targets `reapy`, `curl_cffi`, builtins, or another extension/dynamic API directly.
- [ ] 3.3 Express the third-render failure with wrapture's scoped behavior where it is clearer than the current mutable call counter, and assert render ordering or the absence of later work after failure; verify an unconfigured collaborator call and invalid argument shape fail loudly rather than fabricate a value.
- [ ] 3.4 Run the comparison twice in one pytest invocation and inspect the two test setups; verify every binding is removed after success and failure, and record whether the wrapture version is at least as understandable and reduces the hand-written fake surface enough to justify a follow-up fixture migration.

## 4. Document and validate the adoption boundary

- [ ] 4.1 Create `tests/README.md` with concise contributor guidance describing when to choose wrapture (real control-flow/order or absence assertions across project-owned Python methods, including the upload and render comparisons) and when to retain `mock` or `monkeypatch`; verify it excludes direct bindings on reapy/curl-cffi, process, filesystem, environment, and open-ended doubles.
- [ ] 4.2 Document the alpha upgrade, rollback, and render-comparison decision procedure in `tests/README.md`; verify it requires an explicit exact-pin update, focused pilot runs, a full suite run, and removal of the test-only dependency/pilot as the rollback. Add only a short link from the top-level README if needed for discoverability.
- [ ] 4.3 Run `uv run check --fix`, `uv run pytest tests/commands/test_upload.py`, `uv run pytest tests/commands/render/test_render.py`, and `uv run pytest`; verify static checks pass, both focused pilots pass, and the full suite passes with no test isolation failures.
