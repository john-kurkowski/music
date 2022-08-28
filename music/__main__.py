#!/usr/bin/env python


"""CLI for this package."""

import click

from .render import main as _render


@click.group()
def cli() -> None:
    """Miscellaneous tasks for publishing my music."""


@cli.command()
def render() -> None:
    """Render vocal, instrumental versions of current Reaper project."""
    _render()


if __name__ == "__main__":
    cli()
