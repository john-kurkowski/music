"""Open command."""

import subprocess

import click

import music.util


@click.command("open")
def main() -> None:
    """Show the folder containing the current project."""
    project = music.util.ExtendedProject()
    cmd = ["open", project.path]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
