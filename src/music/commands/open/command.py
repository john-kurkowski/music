"""Open command."""

import subprocess

import click

from music.utils.project import ExtendedProject


@click.command("open")
def main() -> None:
    """Show the folder containing the current project."""
    project = ExtendedProject()
    cmd = ["open", project.path]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
