#!/usr/bin/env python


"""CLI for this package."""

from typing import Optional

import click

from .render import SongVersion, main as _render


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
    is_flag=True,
)
@click.option(
    "--include-instrumental",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL,
    help=(
        "Whether to render the instrumental version. Defaults to rendering all"
        ' versions, unless one of the "--include-*" flags is set.'
    ),
    is_flag=True,
)
def render(
    include_main: Optional[SongVersion], include_instrumental: Optional[SongVersion]
) -> None:
    """Render vocal, instrumental versions of the current Reaper project.
    Overwrites existing versions. Note the Reaper preference "Set media items
    offline when application is not active" should be unchecked, or media items
    will be silent in the render."""
    if any(opt is not None for opt in (include_main, include_instrumental)):
        versions = {
            version
            for version in (
                SongVersion.MAIN if include_main else None,
                SongVersion.INSTRUMENTAL if include_instrumental else None,
            )
            if version
        }
        _render(versions)
    else:
        _render()


if __name__ == "__main__":
    cli()
