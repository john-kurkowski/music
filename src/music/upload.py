"""Upload to SoundCloud."""

from pathlib import Path

import requests


def upload(oauth_token: str, files: list[Path]) -> None:
    """Upload the given audio files to SoundCloud.

    Matches the files to SoundCloud tracks by exact filename.
    """
    headers = {
        "Authorization": f"OAuth {oauth_token}",
    }

    tracks_resp = requests.get(
        "https://api-v2.soundcloud.com/users/41506/tracks",
        headers=headers,
        params={"limit": 999},
        timeout=10,
    )
    tracks_resp.raise_for_status()

    filenames = {file.stem for file in files}
    tracks_by_title = {
        track["title"]: track
        for track in tracks_resp.json()["collection"]
        if track["title"] in filenames
    }
    missing_tracks = filenames.difference(tracks_by_title.keys())
    if missing_tracks:
        raise KeyError(f"Tracks to upload not found in SoundCloud: {missing_tracks}")

    # TODO: actually upload from disk
