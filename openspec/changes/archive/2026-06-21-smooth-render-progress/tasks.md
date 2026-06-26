## 1. Resolve Projection Policy

- [x] 1.1 Choose and record the observed-rate estimator, stale threshold, final projection ceiling, and implausible-rate bound in `design.md` before changing application code.
- [x] 1.2 Decide whether the 0.5-second authoritative measurement interval remains universal for this change; keep format-specific cadence changes out of scope unless explicitly added to the spec.

## 2. Projection State Tests

- [x] 2.1 Add deterministic tests with fixed monotonic timestamps for linear projection from two valid measurements and no interpolation from one measurement.
- [x] 2.2 Add tests proving displayed progress never regresses, projections stop when stale, and projected progress never reaches one.
- [x] 2.3 Add tests proving malformed, decreasing, out-of-range, and implausible measurements are handled safely without corrupting the observed rate.
- [x] 2.4 Add tests proving explicit success reports exactly one and failure preserves the last displayed fraction.

## 3. Projection State Implementation

- [x] 3.1 Introduce a Rich-independent state object that stores the two latest valid duration/time measurements and accepts an injectable monotonic clock.
- [x] 3.2 Implement observed-rate calculation, projection, monotonic reconciliation, clamping, staleness, and terminal-state handling to satisfy the fixed-value tests.

## 4. Monitor Integration

- [x] 4.1 Keep `_rendered_duration` and `_ffprobe` responsible only for authoritative output inspection at the selected measurement interval.
- [x] 4.2 Keep `monitor_render_progress` as lifecycle owner of the measurement loop and add a lightweight display loop that invokes the existing callback near Rich's refresh rate.
- [x] 4.3 Ensure completion and cancellation stop both loops promptly without masking render exceptions.
- [x] 4.4 Add a focused test proving display refreshes do not increase output-duration probe frequency.

## 5. Existing Behavior Coverage

- [x] 5.1 Preserve the WAV and unfinalized-FLAC duration tests.
- [x] 5.2 Preserve or update snapshots covering column order, persistent completed render progress, and no progress bar for indeterminate transcoding.

## 6. Verification

- [x] 6.1 Run `uv run check --fix` repo-wide.
- [x] 6.2 Run focused render and upload tests, then the full test suite.
- [x] 6.3 Perform a short real render and confirm smooth movement, no backward jumps, and a persistent full bar on success.
- [x] 6.4 Perform a sufficiently long FLAC stems render and confirm interpolation does not increase `ffprobe` frequency or noticeably increase CPU usage.
