#!/usr/bin/env python


"""CLI for this package."""

import importlib
from pathlib import Path

import click


@click.group(name="music")
def cli() -> None:
    """Tasks for publishing my music."""


for command_file in (Path(__file__).parent / "commands").glob("*.py"):
    command_name = command_file.stem
    is_a_command = command_name not in ("__init__",)
    if not is_a_command:
        continue
    command_module = importlib.import_module(f"music.commands.{command_name}")
    cli.add_command(command_module.main)


if __name__ == "__main__":  # pragma: no cover
    cli()
