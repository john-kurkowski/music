"""Render processing classes and functions."""

import contextlib
import datetime
import math
import random
import re
import shutil
import subprocess
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Iterator
from functools import cached_property
from pathlib import Path
from timeit import default_timer as timer

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy

import rich.box
import rich.console
import rich.progress
import rich.table

from music.__codegen__ import stats
from music.util import (
    ExtendedProject,
    SongVersion,
    recurse_property,
    set_param_value,
)

# RENDER_SETTINGS bit flags
MONO_TRACKS_TO_MONO_FILES = 16
SELECTED_TRACKS_VIA_MASTER = 128

# Experimentally determined dB scale for Reaper's built-in VST: ReaLimit
LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

# The typical loudness of vocals, in dBs, relative to the instrumental
VOCAL_LOUDNESS_WORTH = 2.0

# Common error code found in SWS functions source
SWS_ERROR_SENTINEL = -666


class RenderResult:
    """Summary statistics of an audio render.

    Rounds times to the nearest second. Microseconds are irrelevant for human DAW operators.
    """

    def __init__(  # noqa: D107
        self, fil: Path, render_delta: datetime.timedelta
    ):
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


def _find_stems(project: reapy.core.Project) -> list[reapy.core.Track]:
    """Find tracks to render as stems.

    Skip tracks that are already muted. Skip tracks that contain no media items
    and no FX; they're just for grouping and don't perform any processing on
    the final mix.
    """
    return [
        track
        for track in project.tracks
        if not track.is_muted and bool(track.items) or bool(len(track.fxs))
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
def _disable_fx(tracks: Collection[reapy.core.Track]) -> Iterator[None]:
    """Disable all effects in the given collection of tracks, then enable them."""
    fxs = [
        fx
        for track in tracks
        for i in range(len(track.fxs))
        if (fx := track.fxs[i]) and fx.is_enabled
    ]
    for fx in fxs:
        fx.disable()
    yield
    for fx in fxs:
        fx.enable()


@contextlib.contextmanager
def _mute(tracks: Collection[reapy.core.Track]) -> Iterator[None]:
    """Mute all tracks in the given collection, then unmute them."""
    for track in tracks:
        track.mute()
    yield
    for track in tracks:
        track.unmute()


def summary_stats_for_file(fil: Path, verbose: int = 0) -> dict[str, float | str]:
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


async def render_version(
    project: ExtendedProject, version: SongVersion
) -> RenderResult:
    """Trigger Reaper to render the current project audio. Returns the output file.

    Names the output file according to the given version. Writes to a temporary
    file first, then overwrites any existing file of the same song version.

    Avoids FX tail leaking issues by tweaking certain, global Reaper
    preferences. Resets them after render completion.
    """
    out_name = version.name_for_project_dir(Path(project.path))

    # Avoid "Overwrite" "Render Warning" dialog, which can't be scripted, with a temporary filename
    rand_id = random.randrange(10**5, 10**6)
    in_name = f"{out_name} {rand_id}.tmp"

    # Avoid FX tails at the beginning of the render
    prev_runafterstop = reapy.reascript_api.SNM_GetIntConfigVar(  # type: ignore[attr-defined]
        "runafterstop", SWS_ERROR_SENTINEL
    )
    prev_runallonstop = reapy.reascript_api.SNM_GetIntConfigVar(  # type: ignore[attr-defined]
        "runallonstop", SWS_ERROR_SENTINEL
    )
    reapy.reascript_api.SNM_SetIntConfigVar("runafterstop", 0)  # type: ignore[attr-defined]
    reapy.reascript_api.SNM_SetIntConfigVar("runallonstop", 0)  # type: ignore[attr-defined]

    prev_render_settings = None
    if version == SongVersion.STEMS:
        prev_render_settings = project.get_info_value("RENDER_SETTINGS")
        project.set_info_value(
            "RENDER_SETTINGS",
            MONO_TRACKS_TO_MONO_FILES | SELECTED_TRACKS_VIA_MASTER,
        )

    pattern = Path(in_name).joinpath(*version.pattern)
    project.set_info_string("RENDER_PATTERN", str(pattern))
    time_start = timer()
    try:
        await project.render()
        time_end = timer()
    finally:
        project.set_info_string("RENDER_PATTERN", "$project")

        if prev_render_settings is not None:
            project.set_info_value("RENDER_SETTINGS", prev_render_settings)

        reapy.reascript_api.SNM_SetIntConfigVar("runafterstop", prev_runafterstop)  # type: ignore[attr-defined]
        reapy.reascript_api.SNM_SetIntConfigVar("runallonstop", prev_runallonstop)  # type: ignore[attr-defined]

    out_fil = version.path_for_project_dir(Path(project.path))
    shutil.move(out_fil.with_stem(in_name), out_fil)

    return RenderResult(out_fil, datetime.timedelta(seconds=time_end - time_start))


def trim_silence(fil: Path) -> None:
    """Trim leading and trailing silence from the given audio file, in-place.

    H/T https://superuser.com/a/1715017
    """
    leading_silence_duration_s = 1.0
    trailing_silence_duration_s = 3.0

    rand_id = random.randrange(10**5, 10**6)
    tmp_fil = f"{fil} {rand_id}.tmp.wav"

    cmd: list[str | Path] = [
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


async def _render_main(
    project: ExtendedProject, vocals: reapy.core.Track | None, verbose: int
) -> RenderResult:
    if vocals:
        vocals.unsolo()
        vocals.unmute()
    return await render_version(project, SongVersion.MAIN)


async def _render_instrumental(
    project: ExtendedProject,
    vocals: reapy.core.Track,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    with (
        _adjust_master_limiter_threshold(project, vocal_loudness_worth),
        _mute((vocals,)),
    ):
        return await render_version(project, SongVersion.INSTRUMENTAL)


async def _render_a_cappella(
    project: ExtendedProject,
    vocal_loudness_worth: float,
    verbose: int,
) -> RenderResult:
    tracks_to_mute = _find_acappella_tracks_to_mute(project)

    with (
        _adjust_master_limiter_threshold(project, vocal_loudness_worth),
        _mute(tracks_to_mute),
    ):
        out = await render_version(project, SongVersion.ACAPPELLA)

    trim_silence(out.fil)
    return out


async def _render_stems(
    project: ExtendedProject,
    vocals: reapy.core.Track | None,
    verbose: int,
) -> RenderResult:
    if vocals:
        vocals.unsolo()
        vocals.unmute()
    for track in project.tracks:
        track.unselect()
    for track in _find_stems(project):
        track.select()
    with _disable_fx([project.master_track]):
        return await render_version(project, SongVersion.STEMS)


class Process:
    """Encapsulate the state of rendering a Reaper project."""

    def __init__(self, console: rich.console.Console) -> None:
        """Initialize."""
        self.console = console

    async def process(
        self,
        project: ExtendedProject,
        versions: Collection[SongVersion],
        vocal_loudness_worth: float | None,
        verbose: int,
    ) -> AsyncIterator[tuple[SongVersion, RenderResult]]:
        """Render the given versions of the given Reaper project.

        Returns render results if anything was rendered. Skips versions that have
        no output. For example, if a project does not have vocals, rendering an a
        capella or instrumental version are skipped.
        """
        vocals = next(
            (track for track in project.tracks if track.name == "Vocals"), None
        )

        if vocal_loudness_worth is None:
            vocal_loudness_worth = float(
                project.metadata.get("vocal-loudness-worth") or VOCAL_LOUDNESS_WORTH
            )

        def add_task(version: SongVersion) -> rich.progress.TaskID:
            return self.progress.add_task(
                f'Rendering "{version.name_for_project_dir(Path(project.path))}"',
                start=False,
                total=1,
            )

        results = []

        if SongVersion.MAIN in versions:
            results.append(
                (
                    SongVersion.MAIN,
                    lambda: _render_main(project, vocals, verbose),
                    add_task(SongVersion.MAIN),
                )
            )

        if SongVersion.INSTRUMENTAL in versions and vocals:
            results.append(
                (
                    SongVersion.INSTRUMENTAL,
                    lambda: _render_instrumental(
                        project,
                        vocals,
                        vocal_loudness_worth,
                        verbose,
                    ),
                    add_task(SongVersion.INSTRUMENTAL),
                )
            )

        if SongVersion.ACAPPELLA in versions and vocals:
            results.append(
                (
                    SongVersion.ACAPPELLA,
                    lambda: _render_a_cappella(project, vocal_loudness_worth, verbose),
                    add_task(SongVersion.ACAPPELLA),
                )
            )

        if SongVersion.STEMS in versions:
            results.append(
                (
                    SongVersion.STEMS,
                    lambda: _render_stems(project, vocals, verbose),
                    add_task(SongVersion.STEMS),
                )
            )

        for i, (version, render, task) in enumerate(results):
            if i > 0:
                self.console.print()

            self.progress.start_task(task)

            yield (
                version,
                await self._print_stats_for_render(project, version, verbose, render),
            )

            self.progress.update(task, advance=1)

        if len(results):
            # Render causes a project to have unsaved changes, no matter what. Save the user a step.
            project.save()

    @cached_property
    def progress(self) -> rich.progress.Progress:
        """Rich progress bar."""
        return rich.progress.Progress(
            rich.progress.SpinnerColumn(),
            rich.progress.TextColumn("{task.description}"),
            rich.progress.TimeElapsedColumn(),
        )

    async def _print_stats_for_render(
        self,
        project: ExtendedProject,
        version: SongVersion,
        verbose: int,
        render: Callable[[], Awaitable[RenderResult]],
    ) -> RenderResult:
        """Collect and print before and after summary statistics for the given project version render.

        Returns the rendered file, after pretty printing itsprogress and metadata.
        """
        name = version.name_for_project_dir(Path(project.path))
        out_fil = version.path_for_project_dir(Path(project.path))

        before_stats = summary_stats_for_file(out_fil) if out_fil.is_file() else {}
        out = await render()
        after_stats = (
            summary_stats_for_file(out_fil, verbose) if out_fil.is_file() else {}
        )

        self.console.print(f"[b default]{name}[/b default]")
        self.console.print(f"[default dim italic]{out.fil}[/default dim italic]")

        table = rich.table.Table(
            box=rich.box.MINIMAL,
            caption=(
                f"Rendered in [b]{out.render_delta}[/b], a"
                f" [b]{out.render_speedup:.1f}x[/b] speedup"
            ),
        )
        table.add_column("", style="blue")
        table.add_column("Before", header_style="bold blue")
        table.add_column("After", header_style="bold blue")

        keys = sorted({k for di in (before_stats, after_stats) for k in di})
        for k in keys:
            table.add_row(
                k, *[str(di.get(k, "")) for di in (before_stats, after_stats)]
            )

        self.console.print(table)

        return out
