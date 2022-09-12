"""Upload to SoundCloud."""

from pathlib import Path

import requests


def upload(oauth_token: str, files: list[Path]) -> None:
    """Upload the given audio files to SoundCloud.

    Matches the files to SoundCloud tracks by exact filename.
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
