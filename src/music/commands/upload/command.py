"""Upload command."""

import email
from pathlib import Path

import aiohttp
import click
import rich.console
import rich.live

import music.utils
from music.utils.project import ExtendedProject
from music.utils.songversion import SongVersion

from .process import Process as UploadProcess


@click.command("upload")
@music.utils.coro
@click.argument(
    "project_dirs",
    nargs=-1,
    type=click.Path(dir_okay=True, exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--additional_headers",
    envvar="SOUNDCLOUD_ADDITIONAL_HEADERS",
    required=False,
    help=(
        "SoundCloud additional HTTP request headers. Read from the environment variable"
        " SOUNDCLOUD_ADDITIONAL_HEADERS."
    ),
)
@click.option(
    "--include-main",
    default=None,
    flag_value=SongVersion.MAIN,
    help=(
        "Whether to include the main version."
        " Defaults to including main, instrumental, and a cappella versions,"
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
        " Defaults to including main, instrumental, and a cappella versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-instrumental-dj",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL_DJ,
    help=(
        "Whether to include the DJ instrumental version."
        " Defaults to including main, instrumental, and a cappella versions,"
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
        " Defaults to including main, instrumental, and a cappella versions,"
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
    additional_headers: str,
    include_main: SongVersion | None,
    include_instrumental: SongVersion | None,
    include_instrumental_dj: SongVersion | None,
    include_acappella: SongVersion | None,
    oauth_token: str,
) -> None:
    """Upload PROJECT_DIRS renders.

    Uploads to SoundCloud. Renders with matching name must exist in SoundCloud
    already, and will be overwritten.

    Defaults to uploading all rendered versions of the currently open project.
    """
    if not oauth_token:
        raise click.MissingParameter(
            param_hint="'SOUNDCLOUD_OAUTH_TOKEN'", param_type="envvar"
        )

    parsed_additional_headers = {**email.message_from_string(additional_headers)}

    if not project_dirs:
        project_dirs = [Path(ExtendedProject().path)]

    versions = {
        version
        for version in (
            include_main,
            include_instrumental,
            include_instrumental_dj,
            include_acappella,
        )
        if version
    } or (
        SongVersion.MAIN,
        SongVersion.INSTRUMENTAL,
        SongVersion.ACAPPELLA,
    )

    files = [
        fil
        for project_dir in project_dirs
        for version in versions
        if (fil := version.path_for_project_dir(project_dir)) and fil.is_file()
    ]

    if not files:
        click.echo("Error: nothing to upload", err=True)
        raise click.exceptions.Exit(2)

    console = rich.console.Console()
    process = UploadProcess(console)
    with rich.live.Live(process.progress, console=console, refresh_per_second=10):
        async with aiohttp.ClientSession() as client:
            uploads = await process.process(
                client, oauth_token, parsed_additional_headers, files
            )

    has_error = False
    for upload in uploads:
        if isinstance(upload, BaseException):
            has_error = True
            click.echo(upload, err=True)

    if has_error:
        raise click.exceptions.Exit(2)
