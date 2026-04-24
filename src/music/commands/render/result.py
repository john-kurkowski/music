"""Helpers for managing and querying render ouput."""

import datetime
import math
import re
import subprocess
from collections.abc import Iterable
from contextlib import AbstractContextManager
from functools import cached_property
from pathlib import Path
from typing import Self

from music.commands.__codegen__ import stats
from music.utils import rm_rf
from music.utils.project import ExtendedProject
from music.utils.songversion import SongVersion


class ExistingRenderResult:
    """Summary statistics of an audio render.

    Rounds times to the nearest second. Microseconds are irrelevant for human DAW operators.
    """

    def __init__(self, project: ExtendedProject, version: SongVersion):
        """Initialize."""
        self.project = project
        self.version = version
        self.fil = version.path_for_project_dir(Path(project.path))

    @property
    def name(self) -> str:
        """Name of the project."""
        return self.version.name_for_project_dir(Path(self.project.path))

    @cached_property
    def summary_stats(self) -> dict[str, float | str]:
        """Statistics for the given audio file, like LUFS-I and LRA."""
        return summary_stats_for_file(self.fil) if self.fil.is_file() else {}


class RenderResult(ExistingRenderResult):
    """Summary statistics of an audio render.

    Rounds times to the nearest second. Microseconds are irrelevant for human DAW operators.
    """

    def __init__(
        self,
        project: ExtendedProject,
        version: SongVersion,
        fil: Path,
        render_delta: datetime.timedelta,
        *,
        cleanup_paths: Iterable[Path] = (),
        eager: bool = False,
    ):
        """Override. Initialize."""
        super().__init__(project, version)
        self.fil = fil
        self.render_delta = datetime.timedelta(seconds=round(render_delta.seconds))
        self._cleanup_paths = tuple(cleanup_paths)

        if eager:
            # Trigger computation eagerly. For example, the input file might be
            # temporary and not exist later.
            self.duration_delta  # noqa: B018
            self.summary_stats  # noqa: B018

    def __enter__(self) -> Self:
        """Support `with`-style lifetime management."""
        return self

    def __exit__(self, *args: object) -> None:
        """Clean up temporary files when the caller is done with this result."""
        self.close()

    def close(self) -> None:
        """Remove any temporary files owned by this render result."""
        for path in self._cleanup_paths:
            rm_rf(path)

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
            return 0.0 if delta_str == "N/A" else float(delta_str)

        fils = self.fil.glob("**/*.wav") if self.fil.is_dir() else [self.fil]
        deltas = [delta_for_audio(fil) for fil in fils]
        return datetime.timedelta(seconds=round(sum(deltas)))

    @property
    def render_speedup(self) -> float:
        """How much faster the render was than the audio file's duration."""
        return (
            (self.duration_delta / self.render_delta) if self.render_delta else math.inf
        )


class ManagedRenderResults(AbstractContextManager["ManagedRenderResults"]):
    """Track render results and close them together when the workflow is done."""

    def __init__(self) -> None:
        """Initialize an empty render result collection."""
        self.renders: list[RenderResult] = []

    def __enter__(self) -> Self:
        """Support `with`-style lifetime management."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close every tracked render result."""
        for render in self.renders:
            render.close()

    def extend(self, renders: Iterable[RenderResult]) -> None:
        """Track more render results for later cleanup."""
        self.renders.extend(renders)


def summary_stats_for_file(fil: Path, *, verbose: int = 0) -> dict[str, float | str]:
    """Print statistics for the given audio file, like LUFS-I and LRA."""
    cmd = _cmd_for_stats(fil)
    proc = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
    proc_output = proc.stderr
    return stats.parse_summary_stats(proc_output)


def _cmd_for_stats(fil: Path) -> list[str | Path]:
    return [
        "ffmpeg",
        "-i",
        fil,
        "-filter:a",
        ",".join(("volumedetect", "ebur128=framelog=verbose")),
        "-hide_banner",
        "-nostats",
        "-f",
        "null",
        "/dev/null",
    ]
