#!/usr/bin/env python


"""CLI for this package."""

import shutil
import warnings
from pathlib import Path

import click

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

import music.render
import music.tag
import music.upload
import music.util

from .codegen import main as _codegen
from .render import (
    SWS_ERROR_SENTINEL,
    VOCAL_LOUDNESS_WORTH,
    SongVersion,
    summary_stats_for_file,
)


@click.group()
def cli() -> None:
    """Tasks for publishing my music."""


@cli.command()
@click.argument(
    "example_audio_file",
    nargs=1,
    required=True,
    type=Path,
)
def codegen(example_audio_file: Path) -> None:
    """Generate code for this package.

    Requires an EXAMPLE_AUDIO_FILE from which to generate a parser.
    """
    _codegen(example_audio_file)


@cli.command()
@click.argument(
    "dst_dir",
    type=click.Path(dir_okay=True, file_okay=False, path_type=Path),
)
@click.argument(
    "files",
    nargs=-1,
    required=True,
    type=click.Path(dir_okay=False, exists=True, file_okay=True, path_type=Path),
)
def export(dst_dir: Path, files: list[Path]) -> None:
    """Export the given FILES to the given DST_DIR directory, in album order."""
    dst_dir.mkdir(exist_ok=True)

    for i, src in enumerate(files):
        dst = dst_dir / f"{i+1:02d} - {src.with_suffix('.wav').name}"
        if dst.exists() and src.stat().st_mtime < dst.stat().st_mtime:
            continue

        shutil.copy2(src, dst)


@cli.command()
@click.argument(
    "project_dirs",
    nargs=-1,
    type=click.Path(dir_okay=True, exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--include-main",
    default=None,
    flag_value=SongVersion.MAIN,
    help=(
        "Whether to render the main version. Defaults to rendering all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-instrumental",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL,
    help=(
        "Whether to render the instrumental version. Rendering this version is skipped"
        " if no vocals exist. Defaults to rendering all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-acappella",
    default=None,
    flag_value=SongVersion.ACAPPELLA,
    help=(
        "Whether to render the a cappella version. Rendering this version is skipped if"
        " no vocals exist. Defaults to rendering all versions, unless"
        ' one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--oauth_token",
    envvar="SOUNDCLOUD_OAUTH_TOKEN",
    help=(
        "SoundCloud OAuth token. Read from the environment variable"
        " SOUNDCLOUD_OAUTH_TOKEN."
    ),
)
@click.option(
    "--upload",
    default=False,
    help="Whether to additionally upload the rendered output to SoundCloud.",
    is_flag=True,
)
@click.option(
    "--vocal-loudness-worth",
    "-vlw",
    default=VOCAL_LOUDNESS_WORTH,
    help=(
        "How many dBs the vocals in the given track account for, to make up when they"
        " are not present, when rendering only the instrumental or a cappella."
        f" Defaults to {VOCAL_LOUDNESS_WORTH}."
    ),
    type=float,
)
def render(
    project_dirs: list[Path],
    include_main: SongVersion | None,
    include_instrumental: SongVersion | None,
    include_acappella: SongVersion | None,
    oauth_token: str,
    upload: bool,
    vocal_loudness_worth: float,
) -> None:
    """Render vocal, instrumental, etc. versions of the given PROJECT_DIRS Reaper projects.

    Defaults to rendering the currently open project.

    Overwrites existing versions. Prints statistics for each output file as it
    is rendered.
    """
    projects = (
        (music.util.ExtendedProject.get_or_open(path) for path in project_dirs)
        if project_dirs
        else [music.util.ExtendedProject()]
    )

    offlineinact = reapy.reascript_api.SNM_GetIntConfigVar("offlineinact", SWS_ERROR_SENTINEL)  # type: ignore[attr-defined]
    if offlineinact != 0:
        raise click.UsageError(
            'Reaper preference "Set media items offline when application is not active"'
            " must be unchecked, or media items will be silent in the render."
        )

    versions = {
        version
        for version in (include_main, include_instrumental, include_acappella)
        if version
    } or set(SongVersion)

    renders = [
        music.render.main(project, versions, vocal_loudness_worth, verbose=0)
        for project in projects
    ]

    if not any(renders):
        raise click.UsageError("nothing to render")

    if upload:
        music.upload.main(
            oauth_token,
            [version.fil for render in renders for version in render.values()],
        )


@cli.command()
@click.argument("files", nargs=-1, type=Path)
@click.option("--verbose", "-v", count=True)
def stat(files: list[Path], verbose: int) -> None:
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


@cli.command()
@click.argument(
    "file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
def tag(file: Path) -> None:
    """Encode .wav FILE to .mp3 and tag with artist, album, and track number."""
    music.tag.main(file)


@cli.command()
@click.argument(
    "files",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--oauth_token",
    envvar="SOUNDCLOUD_OAUTH_TOKEN",
    help=(
        "SoundCloud OAuth token. Read from the environment variable"
        " SOUNDCLOUD_OAUTH_TOKEN."
    ),
)
def upload(files: list[Path], oauth_token: str) -> None:
    """Upload rendered output FILES to SoundCloud.

    Defaults FILES to all rendered versions of the currently open project.
    """
    if not files:
        project = music.util.ExtendedProject()
        project_dir = Path(project.path)
        files = [
            fil
            for version in SongVersion
            if (fil := project_dir / f"{version.name_for_project_dir(project_dir)}.wav")
            and fil.exists()
        ]

    music.upload.main(oauth_token, files)


if __name__ == "__main__":  # pragma: no cover
    cli()
