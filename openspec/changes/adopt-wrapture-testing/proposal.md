## Why

The test suite relies heavily on broad `unittest.mock` substitutes at boundaries
where test failures can be caused by fabricated values rather than the command
logic. wrapture can instead wrap this project's real Python methods, allowing a
small set of tests to assert the actual call tree, order, arguments, and
negative error-path behavior while retaining the real code around the isolated
external operation.

wrapture is still a pre-1.0 alpha. Its documented API is expected to carry to
1.0, but its authors explicitly need real-world feedback. Adoption must
therefore be developer-only, deliberately small, and reversible rather than a
suite-wide mocking migration or production instrumentation initiative.

## What Changes

- Add wrapture as an exact, development-only test dependency and commit its
  locked transitive dependencies.
- Establish a local test-helper convention that uses function-scoped context
  managers or yield fixtures for every binding, keeping patch lifecycle owned
  by one scope.
- Convert a small, behavior-focused pilot in the upload/HTTP path to bindings
  on this repository's own Python classes. The pilot will keep the real upload
  orchestration running while stubbing only outbound `ClientSession` methods,
  and will assert meaningful cross-method ordering and required non-events on
  an error path.
- Compare one high-value render scenario with the existing REAPER fixture and
  a wrapture-based alternative. Use the result as an explicit gate for any
  later fixture migration, rather than treating snapshot churn or the current
  fakes as a reason to preserve them.
- Retain `unittest.mock` and pytest's `monkeypatch` where the comparison shows
  that broad fabricated collaborators, dynamic `reapy` objects,
  third-party/C-extension boundaries, filesystem/process simulation, or
  environment setup remain the clearer and more reliable choice.
- Do not enable wrapture's pytest plugin, config-driven tracing, autowrapt,
  OpenTelemetry export, or production instrumentation in this change.
- Document the alpha-version upgrade policy and removal path: upgrades are
  explicit, run the focused pilot and full test suite, and may be reverted by
  removing the test extra and pilot helpers without changing application code.

## Capabilities

### New Capabilities

None. This is developer test tooling and does not alter a user-visible product
contract.

### Modified Capabilities

None.

## Impact

- `pyproject.toml` and `uv.lock`: a testing-only alpha dependency, pinned for
  deliberate upgrades rather than accepting a moving pre-release.
- Selected upload and render tests, the render fixture, and a new
  `tests/README.md`: narrowly scoped bindings, strict collaborators where their
  surface is stable, and event/tape assertions where the test benefit exceeds
  the extra mechanism, plus the rule for choosing them. The top-level README
  remains focused on general setup and test commands.
- No production source imports, no CLI behavior, and no release/runtime
  dependency changes.
- Suitability boundary: binding Python-defined `ClientSession`, upload, and
  render-orchestration methods is safe to pilot. Directly patching `reapy`,
  `curl_cffi`, builtins, extension types, dynamically provided attributes,
  module imports before resolution, or work that moves to threads/executors is
  unsuitable or requires special handling. The render comparison may use
  strict stand-ins for a stable, named collaborator surface, but must retain
  another test tool for direct REAPER API access that cannot be represented
  safely.
