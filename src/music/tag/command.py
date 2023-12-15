"""Encode & tag command."""

from pathlib import Path

import click

from .process import main as _tag


@click.command("tag")
@click.argument(
    "file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
def main(file: Path) -> None:
    """Encode .wav FILE to .mp3 and tag with artist, album, and track number."""
    _tag(file)
