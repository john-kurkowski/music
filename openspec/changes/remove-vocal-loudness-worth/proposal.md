## Why

The `vocal-loudness-worth` adjustment encodes an opinionated loudness compensation into default renders, which makes instrumental, DJ instrumental, and a cappella outputs differ from the project mix without an explicit current choice by the user. Removing it makes render output reflect the project state directly and avoids carrying a project-notes setting that no longer has a clear owner.

## What Changes

- **BREAKING**: Remove the `music render --vocal-loudness-worth` / `-vlw` option.
- **BREAKING**: Stop automatically adjusting the master limiter threshold when rendering versions that mute vocal content.
- **BREAKING**: Stop reading `vocal-loudness-worth` from Reaper project notes.
- Remove project metadata parsing once it has no remaining consumers.
- Bump the package major version from `2.0.0` to `3.0.0` because the same project and command can now produce permanently different rendered audio.
- Leave any future direct master limiter threshold option out of this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `render`: Removes vocal-loudness compensation from the render contract for reduced song versions.

## Impact

- `music render` CLI options and help output.
- Render processing for instrumental, DJ instrumental, and a cappella versions.
- Reaper project utility code that currently parses project-note metadata.
- Render tests and snapshots that currently expect metadata lookups and limiter threshold changes.
- Render OpenSpec requirements and package version metadata.
