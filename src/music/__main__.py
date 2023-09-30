#!/usr/bin/env python


"""CLI for this package."""

from pathlib import Path

import click

from .codegen import main as _codegen
from .render import VOCAL_LOUDNESS_WORTH, SongVersion, print_summary_stats
from .render import main as _render


@click.group()
def cli() -> None:
    """Miscellaneous tasks for publishing my music."""


@cli.command()  # type: ignore[attr-defined,arg-type]
@click.argument(
    "example_audio_file",
    nargs=1,
    required=True,
    type=Path,
)
def codegen(example_audio_file: Path) -> None:
    """Generate code for this package.

    Requires an EXAMPLE_AUDIO_FILE from which to generate a parser.
    """
    _codegen(example_audio_file)


@cli.command()  # type: ignore[attr-defined,arg-type]
@click.argument(
    "project_dirs",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--include-main",
    default=None,
    flag_value=SongVersion.MAIN,
    help=(
        "Whether to render the main version. Defaults to rendering all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-instrumental",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL,
    help=(
        "Whether to render the instrumental version. Rendering this version is skipped"
        " if no vocals exist. Defaults to rendering all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-acappella",
    default=None,
    flag_value=SongVersion.ACAPPELLA,
    help=(
        "Whether to render the a cappella version. Rendering this version is skipped if"
        " no vocals exist. Defaults to rendering all versions, unless"
        ' one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--vocal-loudness-worth",
    "-vlw",
    default=VOCAL_LOUDNESS_WORTH,
    help=(
        "How many dBs the vocals in the given track account for, to make up when they"
        " are not present, when rendering only the instrumental or a cappella."
        f" Defaults to {VOCAL_LOUDNESS_WORTH}."
    ),
    type=float,
)
def render(
    project_dirs: list[Path],
    include_main: SongVersion | None,
    include_instrumental: SongVersion | None,
    include_acappella: SongVersion | None,
    vocal_loudness_worth: float,
) -> None:
    """Render vocal, instrumental, etc. versions of the given PROJECT_DIRS Reaper projects.

    Defaults to rendering the currently open project.

    Overwrites existing versions. Prints statistics for each output file as it
    is rendered.

    Note the Reaper preference "Set media items offline when application is not
    active" should be unchecked, or media items will be silent in the render.
    """
    versions = {
        version
        for version in (include_main, include_instrumental, include_acappella)
        if version
    } or None
    _render(project_dirs, versions, vocal_loudness_worth)


@cli.command()  # type: ignore[attr-defined,arg-type]
@click.argument("files", nargs=-1, required=True, type=Path)
@click.option("--verbose", "-v", count=True)
def stat(files: list[Path], verbose: int) -> None:
    """Print statistics for the given audio files, like LUFS-I and LRA."""
    for i, fil in enumerate(files):
        if i > 0:
            print()
        if len(files) > 1:
            print(fil)
        print_summary_stats(fil, verbose)
