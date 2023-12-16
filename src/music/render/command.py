"""Render command."""

import asyncio
import warnings
from pathlib import Path

import aiohttp
import click

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


import music.upload.process
import music.util

from .process import (
    SWS_ERROR_SENTINEL,
    VOCAL_LOUDNESS_WORTH,
    SongVersion,
)


@click.command("render")
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
        "Whether to include the instrumental version. This version is skipped"
        " if no vocals exist. Defaults to including all versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-acappella",
    default=None,
    flag_value=SongVersion.ACAPPELLA,
    help=(
        "Whether to include the a cappella version. This version is skipped if"
        " no vocals exist. Defaults to including all versions, unless"
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
async def main(
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

    offlineinact = reapy.reascript_api.SNM_GetIntConfigVar(  # type: ignore[attr-defined]
        "offlineinact", SWS_ERROR_SENTINEL
    )
    if offlineinact != 0:
        raise click.UsageError(
            'Reaper preference "Set media items offline when application is not active"'
            " must be unchecked, or media items will be silent in the render."
        )

    versions = {
        version
        for version in (include_main, include_instrumental, include_acappella)
        if version
    } or list(SongVersion)

    renders = []
    uploads = []

    async with aiohttp.ClientSession() as client:
        for project in projects:
            for _, render in music.render.process.main(
                project, versions, vocal_loudness_worth, verbose=0
            ):
                renders.append(render)

                if upload:
                    uploads.append(
                        music.upload.process.main(client, oauth_token, [render.fil])
                    )

        await asyncio.gather(*uploads)

    if not renders:
        raise click.UsageError("nothing to render")
