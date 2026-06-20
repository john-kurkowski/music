## ADDED Requirements

### Requirement: Authoritative progress measurements
The render monitor SHALL treat successful output-duration probes as the
authoritative source of render progress and SHALL keep probe frequency
independent from display refresh frequency.

#### Scenario: Display refreshes between probes
- **WHEN** the display updates between scheduled output-duration probes
- **THEN** it does not trigger an additional output-duration probe

### Requirement: Projected display progress
The render monitor SHALL project display progress between authoritative
measurements only after two valid measurements establish an observed render rate.

#### Scenario: Only one valid measurement exists
- **WHEN** the monitor has received only one valid progress measurement
- **THEN** display progress remains at the latest measured value

#### Scenario: Two valid measurements exist
- **WHEN** two valid measurements establish rendered-audio seconds per wall-clock second
- **THEN** display progress advances between probes using that observed rate

### Requirement: Safe projection bounds
Projected render progress SHALL remain monotonic, SHALL stay within the range
from zero through one, and SHALL remain below completion until render success is explicit.

#### Scenario: Measurement trails the displayed projection
- **WHEN** a new authoritative measurement is behind the currently displayed progress
- **THEN** displayed progress does not move backward

#### Scenario: Projection reaches the completion margin
- **WHEN** projection would display completed progress before render success
- **THEN** displayed progress remains below one

### Requirement: Stale and invalid measurement handling
The render monitor SHALL stop projection after the latest measurement becomes
stale and SHALL exclude decreasing, malformed, or implausible measurement deltas
from observed-rate calculation.

#### Scenario: Measurements become stale
- **WHEN** no valid measurement arrives within the configured stale threshold
- **THEN** display progress stops advancing until another valid measurement arrives

#### Scenario: Invalid measurement arrives
- **WHEN** a measurement cannot establish a valid forward render rate
- **THEN** it is not used to update the projected rate
- **AND** displayed progress remains within its safe bounds

### Requirement: Terminal render progress
The render monitor SHALL display exactly complete progress only after success and
SHALL preserve the last displayed progress when reporting failure.

#### Scenario: Render succeeds
- **WHEN** the render reports success
- **THEN** displayed progress becomes exactly one

#### Scenario: Render fails
- **WHEN** the render reports failure
- **THEN** the failure indicator retains the last displayed progress value
