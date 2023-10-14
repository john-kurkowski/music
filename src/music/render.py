"""Render vocal and instrumental versions of the current Reaper project."""

import contextlib
import datetime
import enum
import math
import pathlib
import random
import re
import shutil
import subprocess
import warnings
from collections.abc import Callable, Collection, Iterator
from functools import cached_property
from timeit import default_timer as timer
from typing import cast

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

import rich.box
import rich.console
import rich.live
import rich.table

from .__codegen__ import stats
from .util import (
    assert_exhaustiveness,
    recurse_property,
    set_param_value,
)

# Experimentally determined dB scale for Reaper's built-in VST: ReaLimit
LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

# The typical loudness of vocals, in dBs, relative to the instrumental
VOCAL_LOUDNESS_WORTH = 2.0

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230

# Common error code found in SWS functions source
SWS_ERROR_SENTINEL = -666

# Test-only property. Set to a large number to avoid text wrapping in the console.
_CONSOLE_WIDTH: int | None = None


class RenderResult:
    """Summary statistics of an audio render.

    Rounds times to the nearest second. Microseconds are irrelevant for human DAW operators.
    """

    def __init__(  # noqa: D107
        self, fil: pathlib.Path, render_delta: datetime.timedelta
    ):
        self.fil = fil
        self.render_delta = datetime.timedelta(seconds=round(render_delta.seconds))

    @cached_property
    def duration_delta(self) -> datetime.timedelta:
        """How long the audio file is."""
        proc = subprocess.run(
            ["ffprobe", "-i", self.fil, "-show_entries", "format=duration"],
            capture_output=True,
            check=True,
            text=True,
        )
        proc_output = proc.stdout
        delta_str = re.search(r"duration=(\S+)", proc_output).group(1)  # type: ignore[union-attr]
        return datetime.timedelta(seconds=round(float(delta_str)))

    @property
    def render_speedup(self) -> float:
        """How much faster the render was than the audio file's duration."""
        return (
            (self.duration_delta / self.render_delta) if self.render_delta else math.inf
        )


class SongVersion(enum.Enum):
    """Different versions of a song to render."""

    MAIN = enum.auto()
    INSTRUMENTAL = enum.auto()
    ACAPPELLA = enum.auto()

    def name_for_project(self, project: reapy.core.Project) -> str:
        """Name of the project for the given song version."""
        project_name = pathlib.Path(project.name).stem
        if self is SongVersion.MAIN:
            return project_name
        elif self is SongVersion.INSTRUMENTAL:
            return f"{project_name} (Instrumental)"
        elif self is SongVersion.ACAPPELLA:
            return f"{project_name} (A Cappella)"
        else:  # pragma: no cover
            assert_exhaustiveness(self)


def _find_acappella_tracks_to_mute(
    project: reapy.core.Project,
) -> list[reapy.core.Track]:
    """Find tracks to mute when rendering the a cappella version of the song.

    reapy.core.Track.solo() doesn't work as expected, so we have to mute
    multiple tracks by hand. Skip tracks that are already muted (wouldn't want
    to ultimately unmute them). Skip tracks that contain no media items
    themselves and still might contribute to the vocal, e.g. sends with FX.
    """

    def is_vocal(track: reapy.Track) -> bool:
        return any(
            track.name == "Vocals" for track in recurse_property("parent_track", track)
        )

    return [
        track
        for track in project.tracks
        if not track.is_muted and bool(track.items) and not is_vocal(track)
    ]


@contextlib.contextmanager
def _adjust_master_limiter_threshold(
    project: reapy.core.Project, vocal_loudness_worth: float
) -> Iterator[None]:
    """Find the master track's master limiter's threshold parameter and adjust its value without the vocal, then set it back to its original value."""
    limiters = [fx for fx in project.master_track.fxs[::-1] if "Limit" in fx.name]
    if not limiters:
        raise ValueError("Master limiter not found")
    limiter = limiters[0]

    def safe_param_name(param: reapy.core.FXParam) -> str:
        """Work around uncaught exception for non-UTF-8 strings in parameter names."""
        try:
            return param.name
        except reapy.errors.DistError as ex:
            if "UnicodeDecodeError" in str(ex):
                return ""
            raise

    thresholds = [
        param for param in limiter.params if "Threshold" in safe_param_name(param)
    ]
    threshold = thresholds[0]
    threshold_previous_value = threshold.normalized
    threshold_louder_value = (
        (threshold_previous_value * LIMITER_RANGE) - vocal_loudness_worth
    ) / LIMITER_RANGE

    set_param_value(threshold, threshold_louder_value)
    yield
    set_param_value(threshold, threshold_previous_value)


@contextlib.contextmanager
def _mute(tracks: Collection[reapy.core.Track]) -> Iterator[None]:
    """Mute all tracks in the given collection, then unmute them."""
    for track in tracks:
        track.mute()
    yield
    for track in tracks:
        track.unmute()


def _print_stats_for_render(
    project: reapy.core.Project,
    version: SongVersion,
    verbose: int,
    render: Callable[[], RenderResult],
) -> None:
    """Collect and print before and after summary statistics for the given project version render."""
    name = version.name_for_project(project)
    out_fil = pathlib.Path(project.path) / f"{name}.wav"

    console = rich.console.Console(width=_CONSOLE_WIDTH)
    with console.status(f'[bold green]Rendering "{name}"'):
        before_stats = summary_stats_for_file(out_fil) if out_fil.exists() else {}
        out = render()
        after_stats = summary_stats_for_file(out_fil, verbose)

    console.print(f"[b default]{name}[/b default]")
    console.print(f"[default dim italic]{out.fil}[/default dim italic]")

    table = rich.table.Table(
        box=rich.box.MINIMAL,
        caption=(
            f"Rendered [b]{out.duration_delta}[/b] in [b]{out.render_delta}[/b], a"
            f" [b]{out.render_speedup:.1f}x[/b] speedup"
        ),
    )
    table.add_column("", style="blue")
    table.add_column("Before", header_style="bold blue")
    table.add_column("After", header_style="bold blue")

    keys = sorted({k for di in (before_stats, after_stats) for k in di})
    for k in keys:
        table.add_row(k, *[str(di.get(k, "")) for di in (before_stats, after_stats)])

    console.print(table)


def summary_stats_for_file(
    fil: pathlib.Path, verbose: int = 0
) -> dict[str, float | str]:
    """Print statistics for the given audio file, like LUFS-I and LRA."""
    cmd = _cmd_for_stats(fil)
    proc = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
    proc_output = proc.stderr
    return stats.parse_summary_stats(proc_output)


def _cmd_for_stats(fil: pathlib.Path) -> list[str | pathlib.Path]:
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


def render_version(project: reapy.core.Project, version: SongVersion) -> RenderResult:
    """Trigger Reaper to render the current project audio. Returns the output file.

    Names the output file according to the given version. Writes to a temporary
    file first, then overwrites any existing file of the same song version.

    Avoids FX tail leaking issues by tweaking certain, global Reaper
    preferences. Resets them after render completion.
    """
    out_name = version.name_for_project(project)

    # Avoid "Overwrite" "Render Warning" dialog, which can't be scripted, with a temporary filename
    rand_id = random.randrange(10**5, 10**6)
    in_name = f"{out_name} {rand_id}.tmp"

    # Avoid FX tails at the beginning of the render
    prev_runafterstop = reapy.reascript_api.SNM_GetIntConfigVar("runafterstop", SWS_ERROR_SENTINEL)  # type: ignore[attr-defined]
    prev_runallonstop = reapy.reascript_api.SNM_GetIntConfigVar("runallonstop", SWS_ERROR_SENTINEL)  # type: ignore[attr-defined]
    reapy.reascript_api.SNM_SetIntConfigVar("runafterstop", 0)  # type: ignore[attr-defined]
    reapy.reascript_api.SNM_SetIntConfigVar("runallonstop", 0)  # type: ignore[attr-defined]

    project.set_info_string("RENDER_PATTERN", in_name)
    time_start = timer()
    try:
        project.perform_action(RENDER_CMD_ID)
        time_end = timer()
    finally:
        project.set_info_string("RENDER_PATTERN", "$project")

        reapy.reascript_api.SNM_SetIntConfigVar("runafterstop", prev_runafterstop)  # type: ignore[attr-defined]
        reapy.reascript_api.SNM_SetIntConfigVar("runallonstop", prev_runallonstop)  # type: ignore[attr-defined]

    out_dir = pathlib.Path(project.path)
    out_fil = out_dir / f"{out_name}.wav"
    shutil.move(out_dir / f"{in_name}.wav", out_fil)

    return RenderResult(out_fil, datetime.timedelta(seconds=time_end - time_start))


def trim_silence(fil: pathlib.Path) -> None:
    """Trim leading and trailing silence from the given audio file, in-place.

    H/T https://superuser.com/a/1715017
    """
    leading_silence_duration_s = 1.0
    trailing_silence_duration_s = 3.0

    rand_id = random.randrange(10**5, 10**6)
    tmp_fil = f"{fil} {rand_id}.tmp.wav"

    cmd: list[str | pathlib.Path] = [
        "ffmpeg",
        "-i",
        fil,
        "-filter:a",
        ",".join(
            (
                "areverse",
                "atrim=start=0.2",
                f"silenceremove=start_periods=1:start_silence={trailing_silence_duration_s}:start_threshold=0.02",
                "areverse",
                "atrim=start=0.2",
                f"silenceremove=start_periods=1:start_silence={leading_silence_duration_s}:start_threshold=0.02",
            )
        ),
        tmp_fil,
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)

    shutil.move(tmp_fil, fil)


def _render_main(
    project: reapy.core.Project, vocals: reapy.core.Track | None, verbose: int
) -> RenderResult:
    if vocals:
        vocals.unsolo()
        vocals.unmute()
    return render_version(project, SongVersion.MAIN)


def _render_instrumental(
    project: reapy.core.Project,
    vocals: reapy.core.Track,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    with (
        _adjust_master_limiter_threshold(project, vocal_loudness_worth),
        _mute((vocals,)),
    ):
        return render_version(project, SongVersion.INSTRUMENTAL)


def _render_a_cappella(
    project: reapy.core.Project,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    tracks_to_mute = _find_acappella_tracks_to_mute(project)

    with (
        _adjust_master_limiter_threshold(project, vocal_loudness_worth),
        _mute(tracks_to_mute),
    ):
        out = render_version(project, SongVersion.ACAPPELLA)

    trim_silence(out.fil)
    return out


def main(
    project: reapy.core.Project,
    versions: Collection[SongVersion],
    vocal_loudness_worth: float,
    verbose: int,
) -> bool:
    """Render the given versions of the given Reaper project.

    Returns True if anything was rendered, False otherwise. For example, if a
    project does not have vocals, rendering an a capella or instrumental
    version are skipped.
    """
    vocals = next((track for track in project.tracks if track.name == "Vocals"), None)

    did_something = False

    if SongVersion.MAIN in versions:
        did_something = True
        _print_stats_for_render(
            project,
            SongVersion.MAIN,
            verbose,
            lambda: _render_main(project, vocals, verbose),
        )

    if SongVersion.INSTRUMENTAL in versions and vocals:
        if did_something:
            print()
        did_something = True
        _print_stats_for_render(
            project,
            SongVersion.INSTRUMENTAL,
            verbose,
            lambda: _render_instrumental(
                project,
                cast(reapy.Track, vocals),
                vocal_loudness_worth,
                verbose,
            ),
        )

    if SongVersion.ACAPPELLA in versions and vocals:
        if did_something:
            print()
        did_something = True
        _print_stats_for_render(
            project,
            SongVersion.ACAPPELLA,
            verbose,
            lambda: _render_a_cappella(project, vocal_loudness_worth, verbose),
        )

    if did_something:
        # Render causes a project to have unsaved changes, no matter what. Save the user a step.
        project.save()

    return did_something
