"""Codegen command."""

from pathlib import Path

import click

from .process import main as _codegen


@click.command("codegen")
@click.argument(
    "example_audio_file",
    nargs=1,
    required=True,
    type=Path,
)
def main(example_audio_file: Path) -> None:
    """Generate code for this package.

    Requires an EXAMPLE_AUDIO_FILE from which to generate a parser.
    """
    _codegen(example_audio_file)
