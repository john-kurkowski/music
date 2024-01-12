"""Stat command."""

from pathlib import Path

import click

import music.render.process
import music.util
from music.util import SongVersion


@click.command("stat")
@click.argument(
    "files_or_project_dirs",
    nargs=-1,
    type=click.Path(dir_okay=True, exists=True, file_okay=True, path_type=Path),
)
@click.option("--verbose", "-v", count=True)
def main(files_or_project_dirs: list[Path], verbose: int) -> None:
    """Print statistics, like LUFS-I and LRA, for the given audio files or Reaper project directories's rendered versions FILES_OR_PROJECT_DIRS.

    Defaults FILES_OR_PROJECT_DIRS to all rendered versions of the currently open project.
    """
    if not files_or_project_dirs:
        files_or_project_dirs = [Path(music.util.ExtendedProject().path)]

    files_nested = [
        [fil] if fil.is_file() else _files_for_project_dir(fil)
        for fil in files_or_project_dirs
    ]
    files = [fil for nest in files_nested for fil in nest]

    for i, fil in enumerate(files):
        if i > 0:
            print()
        if len(files) > 1:
            print(fil)
        for k, v in music.render.process.summary_stats_for_file(fil, verbose).items():
            print(f"{k:<16}: {v:<32}")


def _files_for_project_dir(project_dir: Path) -> list[Path]:
    return [
        fil
        for version in SongVersion
        if (fil := version.path_for_project_dir(project_dir)) and fil.exists()
    ]
