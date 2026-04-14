"""Upload command."""

import email
from pathlib import Path
from typing import Any

import aiohttp
import click
import rich.console
import rich.live

import music.utils
from music.utils.project import ExtendedProject
from music.utils.songversion import SongVersion

from .process import Process as UploadProcess
from .process import UploadItem


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
    "--debug-http",
    default=False,
    help="Print outgoing SoundCloud HTTP requests and responses for debugging.",
    is_flag=True,
)
@click.option(
    "--dry-run",
    default=False,
    help=(
        "Whether to skip SoundCloud upload writes while still checking what"
        " would be uploaded."
    ),
    is_flag=True,
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
    debug_http: bool,
    dry_run: bool,
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

    upload_items = [
        UploadItem(fil, project_dir, version)
        for project_dir in project_dirs
        for version in versions
        if (fil := version.path_for_project_dir(project_dir)) and fil.is_file()
    ]

    if not upload_items:
        click.echo("Error: nothing to upload", err=True)
        raise click.exceptions.Exit(2)

    console = rich.console.Console()
    process = UploadProcess(console)
    trace_configs = [_build_http_debug_trace(console)] if debug_http else []
    with rich.live.Live(process.progress, console=console, refresh_per_second=10):
        async with aiohttp.ClientSession(trace_configs=trace_configs) as client:
            uploads = await process.process(
                client,
                oauth_token,
                parsed_additional_headers,
                upload_items,
                dry_run=dry_run,
            )

    has_error = False
    for upload in uploads:
        if isinstance(upload, BaseException):
            has_error = True
            click.echo(upload, err=True)

    if has_error:
        raise click.exceptions.Exit(2)


def _build_http_debug_trace(console: rich.console.Console) -> aiohttp.TraceConfig:
    """Build an aiohttp trace config for upload HTTP debugging."""
    trace = aiohttp.TraceConfig()

    @trace.on_request_headers_sent.append
    async def on_request_headers_sent(
        _session: aiohttp.ClientSession,
        _trace_config_ctx: Any,
        params: aiohttp.TraceRequestHeadersSentParams,
    ) -> None:
        if params.url.host != "api-v2.soundcloud.com":
            return

        console.print(
            f"[dim]HTTP {params.method} {params.url}[/dim]",
            markup=True,
        )
        for key, value in params.headers.items():
            console.print(
                f"[dim]{key}: {_redact_http_header_value(key, value)}[/dim]",
                markup=True,
            )

    @trace.on_request_end.append
    async def on_request_end(
        _session: aiohttp.ClientSession,
        _trace_config_ctx: Any,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        if params.url.host != "api-v2.soundcloud.com":
            return

        console.print(
            f"[dim]HTTP {params.response.status} {params.method} {params.url}[/dim]",
            markup=True,
        )

    @trace.on_request_exception.append
    async def on_request_exception(
        _session: aiohttp.ClientSession,
        _trace_config_ctx: Any,
        params: aiohttp.TraceRequestExceptionParams,
    ) -> None:
        if params.url.host != "api-v2.soundcloud.com":
            return

        console.print(
            f"[dim]HTTP EXCEPTION {params.method} {params.url}: {params.exception}[/dim]",
            markup=True,
        )

    return trace


def _redact_http_header_value(key: str, value: str) -> str:
    """Redact secrets in debug header output."""
    lower_key = key.lower()
    if lower_key == "authorization":
        return "OAuth <redacted>"
    if lower_key == "x-datadome-clientid":
        return "<redacted>"
    return value
