"""Upload to SoundCloud."""

import time
from pathlib import Path

import requests
import rich.console
import rich.progress

USER_ID = 41506

# Seemingly the minimal metadata of the original track to be sent in an update
# (although the browser version sends all possible fields in the update dialog,
# even if they're not dirty).
_TRACK_METADATA_TO_UPDATE_KEYS = [
    "title",
]


def main(oauth_token: str, files: list[Path]) -> None:
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

    tracks_resp = requests.get(
        f"https://api-v2.soundcloud.com/users/{USER_ID}/tracks",
        headers=headers,
        params={"limit": 999},
        timeout=10,
    )
    tracks_resp.raise_for_status()

    files_by_stem = {file.stem: file for file in files}
    tracks_by_title = {
        track["title"]: track
        for track in tracks_resp.json()["collection"]
        if track["title"] in files_by_stem
    }
    missing_tracks = set(files_by_stem).difference(tracks_by_title.keys())
    if missing_tracks:
        raise KeyError(f"Tracks to upload not found in SoundCloud: {missing_tracks}")

    console = rich.console.Console()
    for stem, fil in files_by_stem.items():
        track = tracks_by_title[stem]

        _upload_one_file_to_track(
            console,
            headers,
            fil,
            track["id"],
            {k: track[k] for k in _TRACK_METADATA_TO_UPDATE_KEYS},
        )

        console.print(track["permalink_url"])


def _upload_one_file_to_track(
    console: rich.console.Console,
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
    with (
        open(fil, "rb") as fobj,
        rich.progress.Progress(
            rich.progress.SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
            console=console,
        ) as progress,
    ):
        progress.add_task(f'[bold green]Uploading "{fil.name}"', total=None)

        prepare_upload_resp = requests.post(
            "https://api-v2.soundcloud.com/uploads/track-upload-policy",
            headers=headers,
            json={"filename": fil.name, "filesize": fil.stat().st_size},
        )
        prepare_upload_resp.raise_for_status()
        prepare_upload = prepare_upload_resp.json()
        put_upload_headers = prepare_upload["headers"]
        put_upload_url = prepare_upload["url"]
        put_upload_uid = prepare_upload["uid"]

        upload_resp = requests.put(
            put_upload_url,
            data=fobj,
            headers=put_upload_headers,
            timeout=60 * 10,
        )
        upload_resp.raise_for_status()

        transcoding_resp = requests.post(
            f"https://api-v2.soundcloud.com/uploads/{put_upload_uid}/track-transcoding",
            headers=headers,
        )
        transcoding_resp.raise_for_status()
        while True:
            transcoding_resp = requests.get(
                f"https://api-v2.soundcloud.com/uploads/{put_upload_uid}/track-transcoding",
                headers=headers,
            )
            transcoding_resp.raise_for_status()
            transcoding = transcoding_resp.json()
            if transcoding["status"] == "finished":
                break
            time.sleep(3)

        confirm_upload_resp = requests.put(
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
