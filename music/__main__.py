#!/usr/bin/env python


"""CLI for this package."""

from pathlib import Path

import click

from .render import SongVersion, print_summary_stats
from .render import main as _render


@click.group()
def cli() -> None:
    """Miscellaneous tasks for publishing my music."""


@cli.command()
@click.option(
    "--include-main",
    default=None,
    flag_value=SongVersion.MAIN,
    help=(
        "Whether to render the main version. Defaults to rendering all versions, unless"
        ' one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-instrumental",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL,
    help=(
        "Whether to render the instrumental version. Rendering this version is skipped"
        " if no vocals exist. Defaults to rendering all versions, unless one of the"
        ' "--include-*" flags is set.'
    ),
    type=SongVersion,
)
def render(
    include_main: SongVersion | None, include_instrumental: SongVersion | None
) -> None:
    """Render vocal, instrumental versions of the current Reaper project.

    Overwrites existing versions. Note the Reaper preference "Set media items
    offline when application is not active" should be unchecked, or media items
    will be silent in the render.

    Prints statistics for each output file as it is rendered.
    """
    versions = {
        version for version in (include_main, include_instrumental) if version
    } or None
    _render(versions)


@cli.command()
@click.argument("files", nargs=-1, required=True, type=Path)
def stat(files: list[Path]) -> None:
    """Print statistics for the given audio files, like LUFS-I and LRA."""
    for fil in files:
        print_summary_stats(fil)


if __name__ == "__main__":
    cli()
