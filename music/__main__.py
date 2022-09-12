#!/usr/bin/env python


"""CLI for this package."""

import click

from .render import main as _render


@click.group()
def cli() -> None:
    """Miscellaneous tasks for publishing my music."""


@cli.command()
def render() -> None:
    """Render vocal, instrumental versions of the current Reaper project.
    Overwrites existing versions. Note the Reaper preference "Set media items
    offline when application is not active" should be unchecked, or media items
    will be silent in the render."""
    _render()


if __name__ == "__main__":
    cli()
