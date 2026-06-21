## Why

`music render` presents two elapsed durations measured across different boundaries,
making correct timing data appear contradictory. The CLI should report one clear
user-facing duration while retaining the narrower timing needed to calculate render
performance.

## What Changes

- Keep the progress row's end-to-end elapsed time as the only visible duration.
- Report render performance as `N.Nx realtime` rather than as a speedup.
- Remove the REAPER-only elapsed duration from the statistics caption.
- Preserve REAPER-only timing internally as the render-rate denominator.

## Capabilities

### New Capabilities

- `render-timing-reporting`: Defines how render duration and render performance are presented and measured.

### Modified Capabilities

None.

## Impact

- Render summary output and its CLI snapshots.
- Internal timing names or documentation may be clarified without changing their semantics.
- No public API or dependency changes.
