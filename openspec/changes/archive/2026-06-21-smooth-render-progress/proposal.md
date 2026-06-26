## Why

Render progress is measured every 0.5 seconds, so the progress bar advances in
visible jumps even though Rich refreshes the display more frequently. Probing the
actively written output more often would make unfinalized FLAC renders
unnecessarily expensive.

## What Changes

- Continue measuring authoritative rendered duration at the existing probe interval.
- Project display-only progress between successful measurements at the console refresh rate.
- Reconcile projections with measurements without moving displayed progress backward.
- Stop stale projections, reserve 100% for successful completion, and preserve progress on failure.
- Keep output probing frequency independent from display refresh frequency.

## Capabilities

### New Capabilities

- `render-progress`: Defines authoritative render measurements, smooth projected display progress, and terminal success or failure behavior.

### Modified Capabilities

None.

## Impact

- Render progress monitoring and callback scheduling.
- Deterministic progress-state tests and nearby CLI snapshots.
- No intended increase in `ffprobe` subprocess, CPU, or I/O frequency.
