#!/usr/bin/env python

"""Encode .wav master to .mp3 and tag with artist, album, and track number.

Example expected input folders and filenames form: 'My Album Title/01 - Song of
Myself.wav', 'My Album Title/02 - Lead Single.wav'.
"""

import subprocess
import sys
from pathlib import Path


def main(infile: Path) -> None:
    """Encode .wav master to .mp3 and tag with artist, album, and track number."""
    outfile = infile.with_suffix(".mp3")
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


if __name__ == "__main__":
    main(Path(sys.argv[1]))
