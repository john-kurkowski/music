"""Helpers for managing and querying render ouput."""

import datetime
import math
import re
import subprocess
from functools import cached_property
from pathlib import Path


class RenderResult:
    """Summary statistics of an audio render.

    Rounds times to the nearest second. Microseconds are irrelevant for human DAW operators.
    """

    def __init__(self, fil: Path, render_delta: datetime.timedelta):
        """Initialize."""
        self.fil = fil
        self.render_delta = datetime.timedelta(seconds=round(render_delta.seconds))

    @cached_property
    def duration_delta(self) -> datetime.timedelta:
        """How long the audio file is.

        If the file a directory, sums the length of all audio files in the
        directory, recursively.
        """

        def delta_for_audio(fil: Path) -> float:
            proc = subprocess.run(
                ["ffprobe", "-i", fil, "-show_entries", "format=duration"],
                capture_output=True,
                check=True,
                text=True,
            )
            proc_output = proc.stdout
            delta_str = re.search(r"duration=(\S+)", proc_output).group(1)  # type: ignore[union-attr]
            return float(delta_str)

        fils = self.fil.glob("**/*.wav") if self.fil.is_dir() else [self.fil]
        deltas = [delta_for_audio(fil) for fil in fils]
        return datetime.timedelta(seconds=round(sum(deltas)))

    @property
    def render_speedup(self) -> float:
        """How much faster the render was than the audio file's duration."""
        return (
            (self.duration_delta / self.render_delta) if self.render_delta else math.inf
        )
