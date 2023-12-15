"""Upload command."""

from pathlib import Path

import aiohttp
import click

import music.util
from music.render.process import SongVersion

from .process import main as _upload


@click.command("upload")
@music.util.coro
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
        "Whether to include the main version. Defaults to including all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-instrumental",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL,
    help=(
        "Whether to include the instrumental version."
        " Defaults to including all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-acappella",
    default=None,
    flag_value=SongVersion.ACAPPELLA,
    help=(
        "Whether to include the a cappella version."
        " Defaults to including all versions, unless"
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
async def main(
    project_dirs: list[Path],
    include_main: SongVersion | None,
    include_instrumental: SongVersion | None,
    include_acappella: SongVersion | None,
    oauth_token: str,
) -> None:
    """Upload rendered output of the PROJECT_DIRS Reaper projects to SoundCloud.

    Defaults to uploading all rendered versions of the currently open project.
    """
    if not project_dirs:
        project_dirs = [Path(music.util.ExtendedProject().path)]

    versions = {
        version
        for version in (include_main, include_instrumental, include_acappella)
        if version
    } or list(SongVersion)

    files = [
        fil
        for project_dir in project_dirs
        for version in versions
        if (fil := project_dir / f"{version.name_for_project_dir(project_dir)}.wav")
        and fil.exists()
    ]

    if not files:
        raise click.UsageError("nothing to upload")

    async with aiohttp.ClientSession() as client:
        await _upload(client, oauth_token, files)
