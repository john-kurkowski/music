"""Upload processing functions."""

import asyncio
import datetime
from collections.abc import AsyncGenerator, Callable
from functools import cached_property
from pathlib import Path
from typing import Any

import aiofiles
import aiohttp
import rich.console
import rich.progress

USER_ID = 41506

# Seemingly the minimal metadata of the original track to be sent in an update
# (although the browser version sends all possible fields in the update dialog,
# even if they're not dirty).
_TRACK_METADATA_TO_UPDATE_KEYS = [
    "title",
]


class Process:
    """Encapsulate the state of uploading audio files."""

    @cached_property
    def console(self) -> rich.console.Console:
        """Rich console."""
        return rich.console.Console()

    async def process(
        self, client: aiohttp.ClientSession, oauth_token: str, files: list[Path]
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
        }

        tracks_resp = await client.get(
            f"https://api-v2.soundcloud.com/users/{USER_ID}/tracks",
            headers=headers,
            params={"limit": 999},
            timeout=10,
        )
        tracks_resp.raise_for_status()

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

        for fil, track in tracks_by_file.items():
            await self._upload_one_file_to_track(
                client,
                headers,
                fil,
                track["id"],
                {k: track[k] for k in _TRACK_METADATA_TO_UPDATE_KEYS},
            )

            self.console.print(track["permalink_url"])

    @cached_property
    def progress(self) -> rich.console.Group:
        """A group of Rich progress bars."""
        return rich.console.Group(self.progress_upload, self.progress_transcode)

    @cached_property
    def progress_upload(self) -> rich.progress.Progress:
        """Progress bar for uploads."""
        return rich.progress.Progress(
            rich.progress.SpinnerColumn(),
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
            rich.progress.SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            console=self.console,
        )

    async def _upload_one_file_to_track(
        self,
        client: aiohttp.ClientSession,
        headers: dict[str, str],
        fil: Path,
        track_id: int,
        track_metadata_to_update: dict[str, str],
    ) -> None:
        """Perform the API requests for the given audio file to become the new version of the existing SoundCloud track.

        1. Request an AWS S3 upload URL.
        2. Upload the audio file there.
        3. Request transcoding of the uploaded audio file.
        4. Poll for transcoding to finish.
        5. Confirm the transcoded file is what we want as the new file. Send the
           minimal metadata of the original track.
        """
        total = fil.stat().st_size
        task = self.progress_upload.add_task(
            f'[bold green]Uploading "{fil.name}"', total=total
        )

        prepare_upload_resp = await client.post(
            "https://api-v2.soundcloud.com/uploads/track-upload-policy",
            headers=headers,
            json={"filename": fil.name, "filesize": fil.stat().st_size},
        )
        prepare_upload_resp.raise_for_status()
        prepare_upload = await prepare_upload_resp.json()
        put_upload_headers = prepare_upload["headers"]
        put_upload_url = prepare_upload["url"]
        put_upload_uid = prepare_upload["uid"]

        upload_resp = await client.put(
            put_upload_url,
            data=_file_reader(
                lambda steps: self.progress_upload.update(task, advance=steps), fil
            ),
            headers=put_upload_headers,
            timeout=60 * 10,
        )
        upload_resp.raise_for_status()

        task = self.progress_transcode.add_task(
            f'[bold green]Transcoding "{fil.name}"', total=1
        )

        transcoding_resp = await client.post(
            f"https://api-v2.soundcloud.com/uploads/{put_upload_uid}/track-transcoding",
            headers=headers,
        )
        transcoding_resp.raise_for_status()
        while True:
            transcoding_resp = await client.get(
                f"https://api-v2.soundcloud.com/uploads/{put_upload_uid}/track-transcoding",
                headers=headers,
            )
            transcoding_resp.raise_for_status()
            transcoding = await transcoding_resp.json()
            if transcoding["status"] == "finished":
                break
            await asyncio.sleep(3)

        confirm_upload_resp = await client.put(
            f"https://api-v2.soundcloud.com/tracks/soundcloud:tracks:{track_id}",
            headers=headers,
            json={
                "track": {
                    **track_metadata_to_update,
                    "replacing_original_filename": fil.name,
                    "replacing_uid": put_upload_uid,
                },
            },
        )
        confirm_upload_resp.raise_for_status()

        self.progress_transcode.update(task, advance=1)


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
