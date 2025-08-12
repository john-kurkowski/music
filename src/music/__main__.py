#!/usr/bin/env python


"""CLI for this package."""

import importlib
from pathlib import Path

import click


@click.group(name="music")
def cli() -> None:
    """Tasks for publishing my music."""


def discover_commands() -> None:
    """Discover CLI commands in this package.

    Finds command modules by their conventional filename and location.
    Registers them with the Click entrypoint, a top-level command group.
    """
    for command_file in Path(__file__).parent.glob("commands/*/command.py"):
        command_package = command_file.parent.name
        command_module = importlib.import_module(
            f"music.commands.{command_package}.command"
        )
        cli.add_command(command_module.main)


discover_commands()

if __name__ == "__main__":  # pragma: no cover
    cli()
