## Context

The completed render output currently exposes both the progress task's
end-to-end elapsed time and `RenderResult.render_delta`, which measures only the
wait for REAPER. Both values are correct, but their labels do not communicate
their different boundaries.

`render_delta` also feeds the useful render-performance ratio, so removing its
display does not imply removing or broadening its internal measurement.

## Goals / Non-Goals

**Goals:**

- Present one unambiguous elapsed duration.
- Preserve render-performance information using established audio terminology.
- Keep render and upload progress layouts consistent.
- Preserve the semantic boundary of REAPER-only timing.

**Non-Goals:**

- Making the progress duration equal to the REAPER-only duration.
- Changing progress task lifetime or `TimeElapsedColumn` behavior.
- Changing how REAPER render duration is measured.

## Decisions

### Keep only the end-to-end duration visible

The statistics caption will omit `render_delta`; the completed progress row
will remain the sole visible elapsed duration. This duration best represents
the wait experienced by the user and preserves the shared render/upload layout.

The rejected alternative was to reset the progress timer immediately before
calling REAPER. That would hide required pre-render work, complicate task
lifecycle handling, and still duplicate elapsed-time information.

### Retain REAPER-only timing internally

The existing timer around `project.render` remains the denominator for render
performance. Including statistics parsing or console-rendering overhead would
make that metric depend on unrelated application work.

### Describe performance as realtime ratio

The statistics caption will use `Rendered at N.Nx realtime` instead of
`speedup`. This names the ratio directly and avoids implying that the visible
elapsed duration is its denominator.

## Risks / Trade-offs

- **Risk:** Internal timing names may still sound end-to-end. → Clarify nearby
  names or documentation only when doing so does not create disproportionate churn.
- **Trade-off:** The visible elapsed duration and internal performance
  denominator retain different boundaries. → Showing only one duration removes
  the apparent contradiction while preserving the technically correct ratio.

## Migration Plan

Update the output and snapshots together. No data, compatibility, or rollback
migration is required; reverting the output change restores the previous behavior.

## Open Questions

None.
