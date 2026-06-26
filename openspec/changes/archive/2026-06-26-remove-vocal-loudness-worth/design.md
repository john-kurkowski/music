## Context

`music render` currently accepts `--vocal-loudness-worth` / `-vlw`, falls back to a `vocal-loudness-worth` value in Reaper project notes, and uses that value to temporarily move the master limiter threshold while rendering instrumental, DJ instrumental, and a cappella versions. This means reduced versions are not rendered directly from the project state; they include an implicit loudness-compensation policy.

The only current consumer of Reaper project-note metadata parsing is this fallback. Once the fallback is removed, the parser has no remaining product behavior to support.

## Goals / Non-Goals

**Goals:**

- Remove the vocal-loudness-worth CLI option and metadata fallback.
- Render vocal-reduced versions without automatic master limiter threshold adjustment.
- Remove project-note metadata parsing after it becomes unused.
- Bump the package major version to reflect permanently different render output for the same project and command.
- Keep the existing version-selection, muting, format, trimming, upload, progress, and lifecycle behavior intact.

**Non-Goals:**

- Do not add a replacement master limiter threshold option in this change.
- Do not add persisted render settings or a project-note writing/reading convention.
- Do not change how vocals and `(vox)` tracks are identified for version applicability.
- Do not change stem rendering behavior.

## Decisions

1. Remove the compensation rather than defaulting it to zero.

   Keeping the CLI option with a zero default would preserve a public knob whose domain model we no longer want to support. Removing it makes the breaking change explicit in help output, tests, and specs.

2. Delete the generic project metadata parser when it becomes unused.

   Although the parser is generic, retaining it without any behavior depending on it creates a misleading extension point and test surface. If a later feature needs project-note metadata, it can reintroduce parsing with requirements that explain the owner and expected format.

3. Keep limiter controls out of scope.

   A direct limiter threshold or threshold-offset option is plausible, but it should be designed around the mechanism it exposes: absolute versus relative values, units, ReaLimit assumptions, missing limiter behavior, and whether settings are temporary or persistent. Separating that from this removal keeps the major-version cleanup small and predictable.

4. Treat this as a major version bump.

   The same `music render` invocation can produce different audio after this change. That observable output difference is more significant than an ordinary CLI cleanup and should be reflected by moving `2.0.0` to `3.0.0`.

## Risks / Trade-offs

- Existing projects relying on `vocal-loudness-worth` notes will render quieter or differently balanced reduced versions. -> Mitigate by making the removal explicit in the proposal, spec delta, release version, CLI help snapshot updates, and tests.
- Removing metadata parsing may discard a convenient future hook. -> Mitigate by keeping the deletion localized; a future feature can add a fresh parser with a documented contract.
- Snapshot updates may hide an unintended render behavior change. -> Mitigate with focused assertions or snapshot inspection showing limiter parameter writes and metadata lookups are gone while version selection and muting behavior remain.
