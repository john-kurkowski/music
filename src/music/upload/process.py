"""Upload processing functions."""

import asyncio
import datetime
from collections.abc import AsyncGenerator, Callable
from functools import cached_property
from pathlib import Path
from typing import Any, TypedDict

import aiofiles
import aiohttp
import rich.box
import rich.console
import rich.progress

USER_ID = 41506

# Seemingly the minimal metadata of the original track to be sent in an update
# (although the browser version sends all possible fields in the update dialog,
# even if they're not dirty).
_TRACK_METADATA_TO_UPDATE_KEYS = [
    "title",
]

# Allow only 1 upload at a time. Home internet upload bandwidth actively hurts
# the completion time of multiple uploads. It is also suspected that concurrent
# mutating requests more likely incur captchas.
_CONCURRENCY = asyncio.Semaphore(1)


class _PrepareUploadResponse(TypedDict):
    headers: dict[str, str]
    uid: str
    url: str


class Process:
    """Encapsulate the state of uploading audio files."""

    def __init__(self, console: rich.console.Console) -> None:
        """Initialize."""
        self.console = console

    async def process(
        self,
        client: aiohttp.ClientSession,
        oauth_token: str,
        additional_headers: dict[str, Any],
        files: list[Path],
    ) -> None:
        """Upload the given audio files to SoundCloud.

        Matches the files to SoundCloud tracks by exact filename. then uploads them
        to SoundCloud sequentially.
        """
        headers = {
            "Accept": "application/json",
            "Authorization": f"OAuth {oauth_token}",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML,"
                " like Gecko) Chrome/105.0.0.0 Safari/537.36"
            ),
            **additional_headers,
        }

        tracks_resp = await client.get(
            f"https://api-v2.soundcloud.com/users/{USER_ID}/tracks",
            headers=headers,
            params={"limit": 999},
            timeout=10,
        )
        await _raise_for_status(tracks_resp)

        files_by_stem = {file.stem: file for file in files}
        tracks_by_title = {
            track["title"]: track
            for track in (await tracks_resp.json())["collection"]
            if track["title"] in files_by_stem
        }
        missing_tracks = sorted(set(files_by_stem).difference(tracks_by_title.keys()))
        if missing_tracks:
            raise KeyError(
                f"Tracks to upload not found in SoundCloud: {missing_tracks}"
            )

        tracks_by_file = {}
        for stem, fil in files_by_stem.items():
            track = tracks_by_title[stem]

            if not _is_track_older_than_file(track, fil):
                self.console.print(f'[yellow]Skipping already uploaded "{fil.name}"')
                continue

            tracks_by_file[fil] = track

        async with asyncio.TaskGroup() as processes:
            for fil, track in tracks_by_file.items():
                processes.create_task(
                    self._upload_one_file_to_track(client, headers, fil, track)
                )

    @cached_property
    def progress(self) -> rich.console.Group:
        """A group of Rich progress bars."""
        return rich.console.Group(
            self.progress_upload, self.progress_transcode, self.results_table
        )

    @cached_property
    def progress_upload(self) -> rich.progress.Progress:
        """Progress bar for uploads."""
        return rich.progress.Progress(
            rich.progress.SpinnerColumn(finished_text="[green]✓[/green]"),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            rich.progress.BarColumn(),
            rich.progress.DownloadColumn(),
            console=self.console,
        )

    @cached_property
    def progress_transcode(self) -> rich.progress.Progress:
        """Progress bar for transcodes."""
        return rich.progress.Progress(
            rich.progress.SpinnerColumn(finished_text="[green]✓[/green]"),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            console=self.console,
        )

    @cached_property
    def results_table(self) -> rich.table.Table:
        """Table of successful uploads."""
        return rich.table.Table(box=rich.box.MINIMAL)

    async def _upload_one_file_to_track(
        self,
        client: aiohttp.ClientSession,
        headers: dict[str, str],
        fil: Path,
        track: dict[str, Any],
    ) -> None:
        """Perform the API requests for the given audio file to become the new version of the existing SoundCloud track.

        1. Request an AWS S3 upload URL.
        2. Upload the audio file there.
        3. Request transcoding of the uploaded audio file.
        4. Poll for transcoding to finish.
        5. Confirm the transcoded file is what we want as the new file. Send the
           minimal metadata of the original track.
        """
        task = self.progress_upload.add_task(
            f'[bold green]Uploading "{fil.name}"', start=False, total=fil.stat().st_size
        )

        async with _CONCURRENCY:
            self.progress_upload.start_task(task)

            upload = await self._prepare_upload(client, headers, fil)
            await self._upload(client, task, fil, upload)

            task = self.progress_transcode.add_task(
                f'[bold green]Transcoding "{fil.name}"', total=1
            )

            await self._transcode(client, headers, upload)
            await self._confirm_upload(client, headers, track, fil, upload)

        self.progress_transcode.update(task, advance=1)

        if not self.results_table.columns:
            self.results_table.add_column("Title", header_style="bold blue")
            self.results_table.add_column("URL", header_style="bold blue", style="blue")

        self.results_table.add_row(
            track["title"],
            f"[link={track['permalink_url']}]{track['permalink_url']}[/link]",
        )

    async def _confirm_upload(
        self,
        client: aiohttp.ClientSession,
        headers: dict[str, str],
        track: dict[str, Any],
        fil: Path,
        upload: _PrepareUploadResponse,
    ) -> None:
        """Confirm the transcoded file is what we want as the new file.

        Send the minimal metadata of the original track.
        """
        track_metadata_to_update = {k: track[k] for k in _TRACK_METADATA_TO_UPDATE_KEYS}
        resp = await client.put(
            f"https://api-v2.soundcloud.com/tracks/soundcloud:tracks:{track['id']}",
            headers=headers,
            json={
                "track": {
                    **track_metadata_to_update,
                    "replacing_original_filename": fil.name,
                    "replacing_uid": upload["uid"],
                },
            },
        )
        await _raise_for_status(resp)

    async def _prepare_upload(
        self, client: aiohttp.ClientSession, headers: dict[str, str], fil: Path
    ) -> _PrepareUploadResponse:
        """Request an AWS S3 upload URL."""
        resp = await client.post(
            "https://api-v2.soundcloud.com/uploads/track-upload-policy",
            headers=headers,
            json={"filename": fil.name, "filesize": fil.stat().st_size},
        )
        await _raise_for_status(resp)
        upload = await resp.json()
        return {
            "headers": upload["headers"],
            "uid": upload["uid"],
            "url": upload["url"],
        }

    async def _transcode(
        self,
        client: aiohttp.ClientSession,
        headers: dict[str, str],
        upload: _PrepareUploadResponse,
    ) -> None:
        """Request transcoding of the uploaded audio file.

        Polls for transcoding to finish.
        """
        resp = await client.post(
            f"https://api-v2.soundcloud.com/uploads/{upload['uid']}/track-transcoding",
            headers=headers,
        )
        await _raise_for_status(resp)
        while True:
            resp = await client.get(
                f"https://api-v2.soundcloud.com/uploads/{upload['uid']}/track-transcoding",
                headers=headers,
            )
            await _raise_for_status(resp)
            transcoding = await resp.json()
            if transcoding["status"] == "finished":
                break
            await asyncio.sleep(3)

    async def _upload(
        self,
        client: aiohttp.ClientSession,
        task: rich.progress.TaskID,
        fil: Path,
        upload: _PrepareUploadResponse,
    ) -> None:
        """Upload the audio file to the prepared upload destination."""
        resp = await client.put(
            upload["url"],
            data=_file_reader(
                lambda steps: self.progress_upload.update(task, advance=steps), fil
            ),
            headers=upload["headers"],
            timeout=60 * 10,
        )
        await _raise_for_status(resp)


async def _raise_for_status(resp: aiohttp.ClientResponse) -> None:
    """Decorate `aiohttp.ClientResponse.raise_for_status()` with response body text.

    The exception raised by `aiohttp.ClientResponse.raise_for_status()`
    normally only provides high level diagnostics, like error code and a brief
    message. The body has more info.
    """
    if resp.ok:
        return

    text = await resp.text()
    try:
        resp.raise_for_status()
    except aiohttp.ClientResponseError as ex:
        ex.message = f'{ex.message} (with body "{text}")'
        raise


async def _file_reader(
    progress: Callable[[int], Any], fil: Path
) -> AsyncGenerator[bytes, None]:
    """Yield chunks of the given file (to a file reading operation, like an async HTTP upload), updating the given progress bar by a number of steps (bytes)."""
    async with aiofiles.open(fil, "rb") as fobj:
        chunk_size = 64 * 1024
        chunk = await fobj.read(chunk_size)
        while chunk:
            progress(len(chunk))
            yield chunk
            chunk = await fobj.read(chunk_size)


def _is_track_older_than_file(track: dict[str, str], fil: Path) -> bool:
    """Return whether the given SoundCloud track is older than the given file."""
    upload_dt = datetime.datetime.fromisoformat(track["last_modified"])

    system_tzinfo = datetime.datetime.now().astimezone().tzinfo
    file_dt = datetime.datetime.fromtimestamp(fil.stat().st_mtime, system_tzinfo)

    return upload_dt < file_dt
