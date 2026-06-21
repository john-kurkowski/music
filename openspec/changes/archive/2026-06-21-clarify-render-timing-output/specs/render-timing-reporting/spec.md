## ADDED Requirements

### Requirement: Single visible elapsed duration
The render command SHALL display the progress task's end-to-end elapsed time as
the only user-visible elapsed duration for a completed render.

#### Scenario: Successful render completes
- **WHEN** a render completes successfully
- **THEN** the completed progress row displays the elapsed task duration
- **AND** the render statistics do not display a second elapsed duration

### Requirement: Realtime render performance
The render command SHALL report render performance as audio duration divided by
the time REAPER spent rendering, expressed as `N.Nx realtime`.

#### Scenario: Render statistics are displayed
- **WHEN** rendered audio duration and REAPER render duration are available
- **THEN** the statistics report their ratio using the text `Rendered at N.Nx realtime`

### Requirement: End-to-end progress timing
The render progress task SHALL retain its end-to-end lifetime and elapsed-time
column so its layout and meaning remain consistent with upload tasks.

#### Scenario: Render task includes surrounding application work
- **WHEN** the CLI performs required work immediately around the REAPER render
- **THEN** that work remains within the progress task's elapsed duration
- **AND** it does not alter the REAPER-only denominator used for realtime performance
