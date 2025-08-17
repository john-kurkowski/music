"""Path command."""

import click

from music.utils.project import ExtendedProject


@click.command("path")
def main() -> None:
    """Print the path to the current project."""
    project = ExtendedProject()
    click.echo(project.path)
