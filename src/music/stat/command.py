"""Stat command."""

from pathlib import Path

import click

import music.util
from music.render.process import summary_stats_for_file
from music.util import SongVersion


@click.command("stat")
@click.argument("files", nargs=-1, type=Path)
@click.option("--verbose", "-v", count=True)
def main(files: list[Path], verbose: int) -> None:
    """Print statistics, like LUFS-I and LRA, for the given audio files FILES.

    Defaults FILES to all rendered versions of the currently open project.
    """
    if not files:
        project_dir = Path(music.util.ExtendedProject().path)
        files = [
            fil
            for version in SongVersion
            if (fil := project_dir / f"{version.name_for_project_dir(project_dir)}.wav")
            and fil.exists()
        ]

    for i, fil in enumerate(files):
        if i > 0:
            print()
        if len(files) > 1:
            print(fil)
        for k, v in summary_stats_for_file(fil, verbose).items():
            print(f"{k:<16}: {v:<32}")
