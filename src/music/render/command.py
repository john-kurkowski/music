"""Render command."""

import asyncio
import dataclasses
import email
import warnings
from collections.abc import Collection, Iterable
from pathlib import Path

import aiohttp
import click
import rich.console
import rich.live
import rich.progress

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


import music.render.process
import music.upload.process
import music.util
from music.util import SongVersion

from .consts import (
    SWS_ERROR_SENTINEL,
    VOCAL_LOUDNESS_WORTH,
)
from .result import RenderResult

# Test-only property. Set to a large number to avoid text wrapping in the console.
_CONSOLE_WIDTH: int | None = None

UploadResult = asyncio.Task[None]


@click.command("render")
@music.util.coro
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
        "Whether to include the main version. Defaults to including main, instrumental, and a cappella versions,"
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
        " if no vocals exist. Defaults to including main, instrumental, and a cappella versions,"
        ' unless one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-instrumental-dj",
    default=None,
    flag_value=SongVersion.INSTRUMENTAL_DJ,
    help=(
        "Whether to include the DJ instrumental version. This version is skipped"
        " if no vocal samples exist. Defaults to including main, instrumental, and a cappella versions,"
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
        " no vocals exist. Defaults to including main, instrumental, and a cappella versions, unless"
        ' one of the "--include-*" flags is set.'
    ),
    type=SongVersion,
)
@click.option(
    "--include-stems",
    default=None,
    flag_value=SongVersion.STEMS,
    help=(
        "Whether to include the mix stems. Defaults to including main, instrumental, and a cappella versions, unless"
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
    "--upload-existing",
    default=False,
    help='Whether to additionally upload existing renders to SoundCloud, unspecified by the "--include-*" flags.',
    is_flag=True,
)
@click.option(
    "--vocal-loudness-worth",
    "-vlw",
    default=None,
    help=(
        "How many dBs the vocals in the given track account for, to make up when they"
        " are not present, when rendering only the instrumental or a cappella."
        " Defaults to the `vocal-loudness-worth` setting in project notes, or"
        f" {VOCAL_LOUDNESS_WORTH} if unset."
    ),
    type=float,
)
async def main(
    project_dirs: list[Path],
    additional_headers: str,
    include_main: SongVersion | None,
    include_instrumental: SongVersion | None,
    include_instrumental_dj: SongVersion | None,
    include_acappella: SongVersion | None,
    include_stems: SongVersion | None,
    oauth_token: str,
    upload: bool,
    upload_existing: bool,
    vocal_loudness_worth: float | None,
) -> None:
    """Render vocal, instrumental, etc. versions of the given PROJECT_DIRS Reaper projects.

    Defaults to rendering the currently open project.

    Overwrites existing versions. Prints statistics for each output file as it
    is rendered.
    """
    if (upload or upload_existing) and not oauth_token:
        raise click.MissingParameter(
            param_hint="'SOUNDCLOUD_OAUTH_TOKEN'", param_type="envvar"
        )

    parsed_additional_headers = {**email.message_from_string(additional_headers)}

    projects = (
        (music.util.ExtendedProject.get_or_open(path) for path in project_dirs)
        if project_dirs
        else [music.util.ExtendedProject()]
    )

    _validate_reaper()

    versions = {
        version
        for version in (
            include_main,
            include_instrumental,
            include_instrumental_dj,
            include_acappella,
            include_stems,
        )
        if version
    } or (SongVersion.MAIN, SongVersion.INSTRUMENTAL, SongVersion.ACAPPELLA)

    command = _Command(
        parsed_additional_headers,
        oauth_token,
        upload,
        upload_existing,
        vocal_loudness_worth,
        projects,
        versions,
    )

    renders, uploads = await command()
    _report(renders, uploads)


@dataclasses.dataclass
class _Command:
    """Wrap parsed command line arguments."""

    additional_headers: dict[str, str]
    oauth_token: str
    upload: bool
    upload_existing: bool
    vocal_loudness_worth: float | None
    projects: Iterable[music.util.ExtendedProject]
    versions: Collection[SongVersion]

    def __post_init__(
        self,
    ) -> None:
        """Initialize properties not provided by the caller."""
        self.console = rich.console.Console(width=_CONSOLE_WIDTH)
        self.render_process = music.render.process.Process(self.console)
        self.upload_process = music.upload.process.Process(self.console)

    async def __call__(self) -> tuple[list[RenderResult], list[BaseException | None]]:
        """Render all given projects."""
        progress_group = rich.console.Group(
            self.render_process.progress, self.upload_process.progress
        )
        with rich.live.Live(
            progress_group, console=self.console, refresh_per_second=10
        ):
            async with aiohttp.ClientSession() as client:
                renders = []
                uploads = []
                async for renders_, uploads_ in (
                    await self._render_project(client, project)
                    for project in self.projects
                ):
                    renders.extend(renders_)
                    uploads.extend(uploads_)
                return renders, await asyncio.gather(*uploads, return_exceptions=True)

    async def _render_project(
        self, client: aiohttp.ClientSession, project: music.util.ExtendedProject
    ) -> tuple[list[RenderResult], list[UploadResult]]:
        """Render a single project.

        Eagerly uploads existing renders, then synchronously renders versions,
        enqueuing further uploads as renders complete.

        Returns a tuple of (renders, uploads).
        """
        renders = []
        uploads = []

        if self.upload_existing:
            uploads.append(
                asyncio.create_task(
                    self.upload_process.process(
                        client,
                        self.oauth_token,
                        self.additional_headers,
                        _existing_render_fils(project, self.versions),
                    )
                )
            )

        async for _, render in self.render_process.process(
            project,
            self.versions,
            self.vocal_loudness_worth,
            verbose=0,
        ):
            renders.append(render)

            if self.upload and render.fil.is_file():
                uploads.append(
                    asyncio.create_task(
                        self.upload_process.process(
                            client,
                            self.oauth_token,
                            self.additional_headers,
                            [render.fil],
                        )
                    )
                )

        return renders, uploads


def _existing_render_fils(
    project: music.util.ExtendedProject, versions: Collection[SongVersion]
) -> list[Path]:
    """Return a project's existing render files to upload.

    Eases uploading newer files when the render was performed separately.
    """
    existing_versions = set(SongVersion).difference(versions)
    return [
        fil
        for version in existing_versions
        if (fil := version.path_for_project_dir(Path(project.path))) and fil.is_file()
    ]


def _report(renders: list[RenderResult], uploads: list[None | BaseException]) -> None:
    has_error = False

    upload_exceptions = [e for e in uploads if isinstance(e, BaseException)]
    if upload_exceptions:
        has_error = True
        for e in upload_exceptions:
            click.echo(e, err=True)

    if not renders:
        has_error = True
        click.echo("Error: nothing to render", err=True)

    if has_error:
        raise click.exceptions.Exit(2)


def _validate_reaper() -> None:
    offlineinact = reapy.reascript_api.SNM_GetIntConfigVar(  # type: ignore[attr-defined]
        "offlineinact", SWS_ERROR_SENTINEL
    )
    if offlineinact != 0:
        click.echo(
            'Reaper preference "Set media items offline when application is not active"'
            " must be unchecked, or media items will be silent in the render.",
            err=True,
        )
        raise click.exceptions.Exit(2)
