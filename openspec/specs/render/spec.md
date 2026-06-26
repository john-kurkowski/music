# render Specification

## Purpose

Defines what the `render` command produces from a Reaper project: which song
versions it renders, the rules for skipping versions that would be empty or
redundant, how output files are named and written, and the surrounding command
lifecycle (settings validation, saving, and exiting the DAW).

Progress display and timing reporting are specified separately in
`render-progress` and `render-timing-reporting`. SoundCloud upload triggered by
the command's `--upload` flags belongs to the upload capability.

## Requirements

### Requirement: Project selection
The render command SHALL render the given project directories, and SHALL render
the currently open project when no directory is given.

#### Scenario: No project directory given
- **WHEN** the command runs with no project directory argument
- **THEN** it renders the project currently open in the DAW

#### Scenario: Project directories given
- **WHEN** one or more project directories are given
- **THEN** the command renders each of them

### Requirement: Default and explicit version selection
The render command SHALL render the main, instrumental, and a cappella versions
by default, and SHALL render only the explicitly requested versions when any
`--include-*` flag is given.

#### Scenario: No version flag given
- **WHEN** the command runs with no `--include-*` flag
- **THEN** it renders the main, instrumental, and a cappella versions

#### Scenario: One or more version flags given
- **WHEN** any `--include-*` flag is given
- **THEN** the command renders exactly the requested versions and no others

### Requirement: Version applicability rules
The render command SHALL skip a requested version whose content cannot exist for
the project, so that empty or duplicate output is never produced.

#### Scenario: Vocal-dependent version without vocals
- **WHEN** the instrumental or a cappella version is requested for a project with no vocals
- **THEN** that version is skipped

#### Scenario: DJ instrumental that would duplicate the instrumental
- **WHEN** the DJ instrumental is requested but the project has no vocal samples beyond the lead vocal
- **THEN** the DJ instrumental is skipped because it would be identical to the instrumental

### Requirement: Reduced versions compensate for removed vocal loudness
The render command SHALL raise the master limiter threshold by the
vocal-loudness-worth amount when rendering a version that mutes vocals, so the
reduced mix is not quieter than the main version.

#### Scenario: Rendering an instrumental or a cappella version
- **WHEN** a version that mutes vocal content is rendered
- **THEN** the master limiter threshold is adjusted by the vocal-loudness-worth amount
- **AND** the amount defaults to the project's `vocal-loudness-worth` note when not given on the command line

### Requirement: Version output naming and files
The render command SHALL name each version's output after the project, suffixed
by the version, and SHALL write a single audio file per version except stems,
which are written as a directory of per-track files.

#### Scenario: Single-file version
- **WHEN** the main, instrumental, DJ instrumental, or a cappella version is rendered
- **THEN** its output is named after the project with the version's suffix
- **AND** the main version uses the bare project name

#### Scenario: Stems version
- **WHEN** the stems version is rendered
- **THEN** its output is a directory of files mirroring the project's track and folder structure

### Requirement: Render output formats
The render command SHALL render each single-file version as a lossless WAV
accompanied by a shareable lossy copy, and SHALL render stems as lossless
archival files with no lossy copy.

#### Scenario: Single-file version
- **WHEN** the main, instrumental, DJ instrumental, or a cappella version is rendered
- **THEN** its output is a lossless WAV
- **AND** a shareable lossy copy is written alongside it

#### Scenario: Stems version
- **WHEN** the stems version is rendered
- **THEN** its files are lossless archival audio with no lossy copy
- **AND** mono sources are kept mono

### Requirement: A cappella silence trimming
The render command SHALL trim leading and trailing silence from the a cappella
output after rendering, so the isolated vocal does not begin or end with dead air.

#### Scenario: A cappella version finishes rendering
- **WHEN** the a cappella version finishes rendering
- **THEN** leading and trailing silence is trimmed from its output

### Requirement: Overwrite existing output safely
The render command SHALL overwrite a version's existing output, rendering first
to a temporary file so an interrupted render does not destroy the prior output.

#### Scenario: Output already exists
- **WHEN** a version is rendered and its output file already exists
- **THEN** the render writes to a temporary file first and then replaces the existing output

### Requirement: Dry run
The render command SHALL perform the render but leave existing output untouched
when `--dry-run` is given, removing any temporary files it created.

#### Scenario: Dry-run render
- **WHEN** the command runs with `--dry-run`
- **THEN** it performs the render and reports statistics
- **AND** it does not overwrite existing output files
- **AND** it removes the temporary files it created

### Requirement: Per-render statistics summary
The render command SHALL print a before-and-after statistics summary for each
rendered version.

#### Scenario: Version finishes rendering
- **WHEN** a version finishes rendering
- **THEN** the command prints the output name and a table comparing prior and new audio statistics

### Requirement: Save after rendering
The render command SHALL save each project after rendering, because rendering
leaves the project with unsaved changes.

#### Scenario: A project finishes rendering
- **WHEN** at least one version of a project has been rendered
- **THEN** the command saves the project

### Requirement: Keep render dialog open on request
The render command SHALL keep Reaper's render dialog open after the final render
only when `--keep-render-dialog-open` is given.

#### Scenario: Flag given across multiple renders
- **WHEN** `--keep-render-dialog-open` is given
- **THEN** the dialog is kept open only after the final render, not after earlier ones

### Requirement: Exit DAW on request
The render command SHALL exit the DAW after all renders succeed only when
`--exit` is given.

#### Scenario: Exit requested
- **WHEN** the command runs with `--exit` and all renders succeed
- **THEN** the DAW is closed after rendering

### Requirement: Global render setting validation
The render command SHALL refuse to render when a global DAW setting would corrupt
the output.

#### Scenario: Offline-on-inactive setting enabled
- **WHEN** the Reaper preference that takes media items offline while the application is inactive is enabled
- **THEN** the command reports the problem and exits without rendering

### Requirement: Nothing-to-render error
The render command SHALL report an error when no version produced output.

#### Scenario: All requested versions were skipped
- **WHEN** no version produced output
- **THEN** the command reports that there was nothing to render and exits with an error
