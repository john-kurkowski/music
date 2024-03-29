"""Encode & tag processing functions."""

import subprocess
from pathlib import Path


def main(infile: Path) -> None:
    """Encode .wav file to .mp3 and tag with artist, album, and track number."""
    outfile = infile.with_suffix(".mp3")
    if outfile.exists() and infile.stat().st_mtime < outfile.stat().st_mtime:
        return

    artist = "Bluu"
    album = infile.parent.name
    num, _, title = infile.stem.partition(" - ")

    subprocess.check_call(
        [
            "lame",
            "--preset",
            "standard",
            "--ta",
            artist,
            "--tl",
            album,
            "--tn",
            num,
            "--tt",
            title,
            infile,
            outfile,
        ]
    )
