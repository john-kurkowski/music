"""Tag command."""

from pathlib import Path

import click

import music.tag


@click.command("tag")
@click.argument(
    "file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
def main(file: Path) -> None:
    """Encode .wav FILE to .mp3 and tag with artist, album, and track number."""
    music.tag.main(file)
