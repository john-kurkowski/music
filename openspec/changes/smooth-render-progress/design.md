## Context

`monitor_render_progress` currently measures rendered audio every 0.5 seconds.
Rich refreshes at approximately 10 Hz, but the progress bar changes only when a
new measurement arrives. Increasing measurement frequency is undesirable:
unfinalized FLAC duration requires packet inspection through `ffprobe`, which
can add subprocess, CPU, and I/O cost during long stem renders.

The design therefore separates authoritative output inspection from cheap,
display-only projection.

## Goals / Non-Goals

**Goals:**

- Make visible progress move at approximately the console refresh rate.
- Preserve the existing output-probe cadence.
- Reconcile projection safely with authoritative measurements.
- Keep timing logic deterministic and independent from Rich.
- Stop all monitoring work promptly on completion or cancellation.

**Non-Goals:**

- Increasing `ffprobe` frequency to make the bar smoother.
- Treating projected values as authoritative render state.
- Predicting completion before the renderer reports success.
- Changing duration extraction for WAV-like or unfinalized FLAC files.

## Decisions

### Separate measurement from display updates

The slow loop continues probing output duration every 0.5 seconds. A lightweight
display loop asks projection state for the current fraction near Rich's 10 Hz
refresh rate and invokes the existing progress callback.

### Isolate projection state

A small Rich-independent state object retains the two most recent valid
measurements: rendered duration and monotonic observation time. It accepts an
injectable monotonic clock so projection behavior can be tested with fixed times.

### Derive and reconcile an observed rate

After two valid measurements, the state calculates rendered-audio seconds per
wall-clock second and projects forward from the latest measurement. Real
measurements remain authoritative, but displayed progress never regresses when
a measurement temporarily trails a projection.

### Bound speculation

Projection is clamped to the valid fraction range and to a final margin below
one. It stops after a stale threshold. Invalid, decreasing, and implausibly
large deltas do not update the observed rate. Explicit success alone sets one;
failure preserves the last displayed value.

### Preserve exception and cancellation behavior

The measurement and display loops share lifecycle ownership in
`monitor_render_progress`. Completion or cancellation stops both promptly, and
monitor cleanup must not replace the render exception.

## Risks / Trade-offs

- **Risk:** A latest-sample rate can visibly jitter as render speed changes. →
  Keep the estimator encapsulated so a short moving average can replace it later.
- **Risk:** Projection can get ahead of actual output. → Never regress the bar,
  cap speculation below completion, and stop projection when stale.
- **Risk:** A second loop complicates cancellation. → Give the monitor one owner
  responsible for stopping and awaiting both loops without masking exceptions.
- **Trade-off:** Holding a projection that is ahead of measurement temporarily
  favors visual monotonicity over showing the latest lower authoritative value.

## Migration Plan

Introduce projection behind the existing progress callback contract. Preserve
the existing duration probes and CLI rendering surface, allowing the projection
state and display loop to be reverted without changing file inspection.

## Open Questions

- Should inexpensive formats eventually use a shorter measurement interval, or
  should 0.5 seconds remain universal?
- Should the estimator use the latest observed rate or a short moving average?
- What stale threshold and final projection ceiling provide the best behavior?
- What upper bound should classify a measurement delta as implausible?
