#!/usr/bin/env python


"""CLI for this package."""

import importlib
from pathlib import Path

import click


@click.group(name="music")
def cli() -> None:
    """Tasks for publishing my music."""


for command_file in Path(__file__).parent.glob("*/command.py"):
    command_package = command_file.parent.name
    command_module = importlib.import_module(f"music.{command_package}.command")
    cli.add_command(command_module.main)


if __name__ == "__main__":  # pragma: no cover
    cli()
