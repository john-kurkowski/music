## REMOVED Requirements

### Requirement: Reduced versions compensate for removed vocal loudness
**Reason**: The render command should no longer apply an opinionated loudness-compensation policy when producing vocal-reduced versions. Reduced versions should reflect the current project mix after the relevant vocal content is muted.

**Migration**: Projects that depended on the old compensation should adjust the Reaper project mix or master limiter settings directly before rendering. The `vocal-loudness-worth` project note and `--vocal-loudness-worth` / `-vlw` CLI option are no longer used.

The render command SHALL raise the master limiter threshold by the
vocal-loudness-worth amount when rendering a version that mutes vocals, so the
reduced mix is not quieter than the main version.

#### Scenario: Rendering an instrumental or a cappella version
- **WHEN** a version that mutes vocal content is rendered
- **THEN** the master limiter threshold is adjusted by the vocal-loudness-worth amount
- **AND** the amount defaults to the project's `vocal-loudness-worth` note when not given on the command line
