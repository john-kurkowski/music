"""Analyze command."""

import base64
from collections.abc import Iterator
from pathlib import Path

import click
import rpp  # type: ignore[import-untyped]

from music.utils import project


@click.command("analyze")
@click.argument(
    "project_dirs",
    nargs=-1,
    type=click.Path(dir_okay=True, exists=True, file_okay=True, path_type=Path),
)
def main(project_dirs: list[Path]) -> None:
    """Analyze projects for problems.

    Prints out a project's VST settings encoded in base64 for human review.
    Sometimes these contain unwanted settings, which are not possible by
    looking at a Reaper .rpp file directly.

    Accepts 0 or more PROJECT_DIRS projects. Defaults to the currently open
    project.
    """
    if not project_dirs:
        project_dirs = [Path(project.ExtendedProject().path)]

    project_fils = [
        project_dir / f"{project_dir.name}.rpp" for project_dir in project_dirs
    ]

    click.echo(
        "\n".join(
            setting
            for project_fil in project_fils
            for setting in iter_encoded_settings(project_fil)
        )
    )


def iter_encoded_settings(project_fil: Path) -> Iterator[str]:
    """Parse a Reaper project and return all VST settings encoded in base64."""
    with open(project_fil) as fil:
        parsed_project = rpp.load(fil)

    vsts = parsed_project.findall(".//VST")
    for vst in vsts:
        successful_decodes = (
            decode for child in vst.children if (decode := b64_ascii(child))
        )
        yield from successful_decodes


def b64_ascii(s: str) -> str | None:
    """Try to decode a base64 string.

    Many VST settings are encoded in Reaper as base64. Return None if it is not
    one of those strings.
    """
    try:
        return base64.b64decode(s).decode("ascii")
    except UnicodeDecodeError:
        return None
