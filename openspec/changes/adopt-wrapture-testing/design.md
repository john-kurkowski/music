## Context

See [proposal.md](proposal.md) for the motivation. The project supports Python
3.12+ and its tests use pytest, syrupy snapshots, `unittest.mock`, and
pytest's `monkeypatch`. The dominant mocks isolate SoundCloud HTTP,
REAPER/reapy, subprocesses, and host configuration. In particular,
`tests/conftest.py` blocks real curl-cffi requests by patching this project's
`ClientSession.request`, while upload tests use `Mock` response trees and
snapshot flat mock-call lists. The suite already treats selected interaction
transcripts as durable test evidence, not merely as implementation detail.

The render suite has a separate `render_mocks` fixture that replaces the
project class, REAPER configuration calls, upload processing, and project/track
objects with hand-built `Mock` graphs. `test_main_mixed_errors` is a useful
representative case: it drives real CLI orchestration, simulates the third of
three renders failing, and asserts the resulting observable command behavior.
The current fixture can be brittle when an unconfigured mock attribute masks a
collaborator-surface change; its value must be measured against an alternative,
not presumed.

wrapture's useful distinction is that it wraps a real named call site and
records its arguments, outcome, nesting, and order; it can still return a
stubbed result or inject a failure. Its [announcement](https://grahamdumpleton.me/posts/2026/08/introducing-wrapture/)
and [mock comparison guide](https://wrapture.readthedocs.io/en/latest/coming-from-mock.html)
describe this as complementary to, rather than a replacement for,
`unittest.mock`.

## Goals / Non-Goals

**Goals:**

- Validate one realistic async upload workflow with wrapture on all supported
  Python versions before allowing any wider use.
- Make the pilot test's protocol and error-path assertions depend on calls that
  occurred, not on chained `MagicMock` values.
- Compare one concise Wrapture tape snapshot with the existing mock-call
  snapshot style, using Wrapture's documented canonical exporter rather than
  private event data or an unstable object representation.
- Make binding lifetime and alpha upgrades explicit, deterministic, and easy to
  remove.
- Compare a wrapture-based render test with the current fixture on a meaningful
  render failure path, and decide wider fixture migration from evidence.

**Non-Goals:**

- Replacing the established test suite, fixture API, snapshots, `mock`, or
  `monkeypatch`.
- Binding extension/builtin types, the dynamically supplied REAPER API, or
  changing the production application to import wrapture.
- Enabling tracing, telemetry export, autowrapt, config-driven patching, or the
  optional pytest plugin.
- Supporting parallel binding of the same target, threads, executor work, or
  forked work in the pilot.
- Binding the dynamic or extension-backed REAPER API directly, or committing to
  a suite-wide render-fixture rewrite before the comparison passes its gate.

## Decisions

### Keep wrapture test-only and pin the alpha exactly

Add `wrapture==1.0.0a21` to the existing `testing` extra, update `uv.lock`, and
do not add it to runtime dependencies. Treat a version bump as a conscious
maintenance change: read its release notes, run the pilot, then run the full
suite. Removing the extra and the pilot is the rollback; application code will
have no import or configuration dependency on it.

The documentation says a plain install selects the latest pre-release until
1.0.0, while also calling for alpha feedback. An exact constraint avoids an
unreviewed alpha API or behavior change entering local development and CI.

Alternative considered: `wrapture>=1.0.0a21,<1.0.0` or an unpinned install.
Rejected because it accepts precisely the pre-release churn this first adoption
is meant to measure. Alternative considered: wait for 1.0. Rejected because a
small, isolated test-only evaluation produces useful evidence with a clean
exit; promotion remains a later decision.

### Pilot this repository's own async HTTP seam first

Add a focused test alongside `tests/commands/test_upload.py`. It will bind
Python-defined methods on `music.utils.http.ClientSession` and, only where it
makes the hierarchy meaningful, the upload `Process`. The test will run the
real upload orchestration but replace the final HTTP operations with explicit,
minimal response objects. A `timeline()` will assert the externally meaningful
request protocol (initial track lookup before an upload request) and an
error-path non-event (no mutation request after a failed prerequisite).

This is a good fit because the upload code schedules coroutines with
`asyncio.create_task`; wrapture documents task-context recording as supported.
The test stays single-threaded and function-scoped. It does not use a tape to
assert every internal helper call or every byte of an HTTP payload; existing
snapshot tests retain broad request-shape coverage.

Alternative considered: rewrite the reusable `requests_mocks` fixture and all
upload snapshots. Rejected because it would turn an evaluation into a broad
fixture migration before the first pilot establishes the library's lifecycle
and async behavior.

### Compare a canonical tape snapshot with mock-call snapshots

Extend one upload pilot with a snapshot of `wrapture.export.canonical(tape)`.
This public exporter is specifically designed for snapshot tests: it renders a
small call tree while omitting unstable sequence numbers, timings, captured
values, and thread identity. The snapshot will cover only the explicitly bound
project-owned methods, so it records the workflow boundary selected by the
test, rather than every incidental internal call.

Keep direct assertions for the narrowly important absence and outcome
contracts. The comparison evaluates whether the canonical tape is clearer and
less coupled to `Mock` child-call plumbing than a flat `mock_calls` snapshot;
it does not replace the existing HTTP request-shape snapshots or assert
Wrapture's internal event implementation. Record the result in the test
guidance, including the rule that a tape snapshot must use a documented public
renderer and remain small enough to review.

Alternative considered: continue with only `tape.assert_order`. Rejected for
this evaluation because it exercises the tape but does not compare its primary
review affordance—a readable interaction transcript—against the suite's
established mock-call snapshots. Alternative considered: snapshot `Tape` or
its private event list. Rejected because the former is only a count summary and
the latter is not a supported alpha API or a stable snapshot contract.

### Compare, rather than exclude, a render-fixture alternative

Add a separate comparison test based on `test_main_mixed_errors`; do not remove
or rewrite that test initially. It must keep the real CLI/render orchestration
and exercise a third-render failure, while replacing only the unavailable
collaborator surface. Prefer a wrapture binding on a project-owned Python render
method and a spec-required collaborator double where its named surface is
stable. Use wrapture's phased behavior to express the third-call failure if
that produces a clearer test than the current mutable call counter.

The comparison must not bind `reapy`, `curl_cffi`, or another extension/dynamic
API directly. A small, explicit remaining fake or a conventional patch at that
boundary is acceptable: the question is whether wrapture reduces the
first-party fake surface and makes the *project's* orchestration test more
truthful, not whether it can make REAPER available in CI.

The comparison passes only if it:

- preserves the existing scenario's observable CLI failure behavior;
- makes use of an unconfigured collaborator result, or an invalid call shape,
  fail loudly rather than fabricate a value or call chain;
- provides a useful assertion for render ordering or the absence of later work
  after the third-render failure;
- removes all bindings after the test, including when the assertion fails; and
- is at least as understandable as the current fixture, with the amount of
  hand-written fake surface recorded as evidence rather than as a rigid
  line-count target.

If it passes, retain the comparison as the canonical render example and plan
any broader migration separately. If it fails, retain the current fixture and
the upload-only adoption; either result is a successful evaluation.

Alternative considered: exclude render because REAPER is unavailable in CI.
Rejected because the current fixture's maintenance cost is itself evidence
worth testing. Alternative considered: immediately rewrite `render_mocks`.
Rejected because a side-by-side scenario is the only reliable way to learn
whether strict wrapping improves this specific object graph.

### Use context-manager ownership and leave leak detection opt-in

Each pilot binding is created in the test and owned by one
`with wrapture.timeline(...)` scope (or a function-scoped yield fixture only if
repetition proves it useful). Configure behavior before entering the scope and
assert events before it exits. Do not share an applied binding across tests,
mix a decorator with a fixture for the same binding, or enable the pytest
plugin in this change.

The test guide guarantees removal on context-manager exit, while warning that
shared bindings retain behavior and cannot be applied concurrently. The
project's test style makes a narrow explicit scope easier to review than a
global plugin rollout. A later proposal may evaluate the plugin after the
pilot has demonstrated that it coexists with the current mock fixtures.

### Maintain a target-selection rule

Use wrapture when a test benefits from observing real control flow across one
or more *Python-defined, already imported* methods and can leave the rest of
the code real. A strict, named collaborator double is also eligible when it can
replace an open-ended mock surface. Continue using the current tools when the
test needs an invented/open-ended collaborator, a module/configuration value,
process/filesystem emulation, environment mutation, or a dynamic/extension API
that has no stable patch point.

Never bind C/builtin or extension types (`curl_cffi` and likely parts of
`reapy`), dynamically served attributes, or work in `threading.Thread`,
executors, or a fork without a separately designed propagation strategy. These
are documented limitations, not failures the pilot should attempt to mask:
[known limitations](https://wrapture.readthedocs.io/en/latest/known-limitations.html).

Alternative considered: expose a generic project-wide `wrapture` fixture.
Rejected because it would make binding a default rather than a justified test
choice and obscure the alpha library's lifecycle boundaries.

## Risks / Trade-offs

- [Alpha behavior or packaging changes] → exact-pin the test extra, lock it,
  document upgrade checks, and keep it absent from production dependencies.
- [A tape snapshot makes refactoring tests brittle] → use the documented
  canonical exporter, bind only the selected workflow boundary, and retain
  direct assertions for narrow absences plus existing snapshots for detailed
  request payloads and CLI output.
- [A binding leaks into following tests] → own each binding in one
  function-scoped context manager; do not add shared applied bindings or the
  pytest plugin during the pilot.
- [Async recording produces an incomplete hierarchy] → prove the selected
  `asyncio.create_task` path under the supported interpreter matrix; if it is
  incomplete, remove the pilot rather than introduce thread/executor
  propagation.
- [The render comparison cannot express the dynamic REAPER surface strictly]
  → retain a small conventional fake at that edge and treat a failure to reduce
  its surface as a no-go for wider migration.
- [External APIs resist patching] → bind only project-owned Python wrapper
  methods; do not directly bind reapy/curl-cffi, subprocess, or filesystem
  boundaries.
- [Two assertion styles confuse maintainers] → add a concise contributor note
  to `tests/README.md` that explains the selection rule and gives the upload
  and render pilots as canonical examples. Keep the top-level README focused
  on general setup and test commands, with only a link to the test guidance if
  discoverability needs it.

## Migration Plan

1. Add the exact test extra and regenerate the lockfile.
2. Add minimal response doubles and the upload pilot; add one canonical tape
   snapshot as a comparison while leaving existing upload fixtures and request
   snapshots unchanged.
3. Add the render comparison beside its current baseline, run both, and record
   the gate outcome before changing the shared render fixture.
4. Run static checks, focused upload and render tests, and the full suite on
   the supported Python matrix.
5. Document the adoption boundary, comparison outcome, and exact
   upgrade/removal procedure.
6. If any lifecycle, async-recording, dependency-resolution, test-isolation,
   or render-comparison gate concern appears, remove the affected pilot and
   dependency in the same change. No application migration or data rollback is
   required.
