"""Render vocal and instrumental versions of the current Reaper project."""

import contextlib
import enum
import pathlib
import random
import shutil
import subprocess
from collections.abc import Collection, Iterator

import click
import reapy

from .__codegen__.stats import parse_summary_stats
from .util import (
    assert_exhaustiveness,
    find_project,
    recurse_property,
    set_param_value,
)

# Experimentally determined dB scale for Reaper's built-in VST: ReaLimit
LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

# The typical loudness of vocals, in dBs, relative to the instrumental
VOCAL_LOUDNESS_WORTH = 2.0

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


class SongVersion(enum.Enum):
    """Different versions of a song to render."""

    MAIN = enum.auto()
    INSTRUMENTAL = enum.auto()
    ACAPPELLA = enum.auto()


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


def print_summary_stats(fil: pathlib.Path, verbose: int = 0) -> None:
    """Print statistics for the given audio file, like LUFS-I and LRA."""
    cmd = _cmd_for_stats(fil)
    proc = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
    proc_output = proc.stderr

    stats = parse_summary_stats(proc_output)
    for k, v in stats.items():
        print(f"{k:<16}: {v:<32}")


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


def render_version(project: reapy.core.Project, version: SongVersion) -> pathlib.Path:
    """Trigger Reaper to render the current project audio. Returns the output file.

    Names the output file according to the given version.
    """
    project_name = pathlib.Path(project.name).stem
    if version is SongVersion.MAIN:
        out_name = project_name
    elif version is SongVersion.INSTRUMENTAL:
        out_name = f"{project_name} (Instrumental)"
    elif version is SongVersion.ACAPPELLA:
        out_name = f"{project_name} (A Cappella)"
    else:  # pragma: no cover
        assert_exhaustiveness(version)

    # Avoid "Overwrite" "Render Warning" dialog, which can't be scripted, with a temporary filename
    rand_id = random.randrange(10**5, 10**6)
    in_name = f"{out_name} {rand_id}.tmp"

    project.set_info_string("RENDER_PATTERN", in_name)
    try:
        project.perform_action(RENDER_CMD_ID)
    finally:
        project.set_info_string("RENDER_PATTERN", "$project")

    out_dir = pathlib.Path(project.path)
    out_fil = out_dir / f"{out_name}.wav"
    shutil.move(out_dir / f"{in_name}.wav", out_fil)
    return out_fil


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
) -> None:
    if vocals:
        vocals.unsolo()
        vocals.unmute()
    out_fil = render_version(project, SongVersion.MAIN)
    print(out_fil)
    print_summary_stats(out_fil, verbose)


def _render_instrumental(
    versions: Collection[SongVersion],
    project: reapy.core.Project,
    vocals: reapy.core.Track,
    vocal_loudness_worth: float,
    verbose: int,
) -> None:
    with (
        _adjust_master_limiter_threshold(project, vocal_loudness_worth),
        _mute((vocals,)),
    ):
        out_fil = render_version(project, SongVersion.INSTRUMENTAL)
        if len(versions) > 1:
            print()
        print(out_fil)
        print_summary_stats(out_fil, verbose)


def _render_a_cappella(
    versions: Collection[SongVersion],
    project: reapy.core.Project,
    vocal_loudness_worth: float,
    verbose: int,
) -> None:
    tracks_to_mute = _find_acappella_tracks_to_mute(project)

    with (
        _adjust_master_limiter_threshold(project, vocal_loudness_worth),
        _mute(tracks_to_mute),
    ):
        out_fil = render_version(project, SongVersion.ACAPPELLA)
        if len(versions) > 1:
            print()
        print(out_fil)
        trim_silence(out_fil)
        print_summary_stats(out_fil, verbose)


def main(
    versions: Collection[SongVersion] | None = None,
    vocal_loudness_worth: float = VOCAL_LOUDNESS_WORTH,
    verbose: int = 0,
) -> None:
    """Render the given versions of the current Reaper project."""
    if versions is None:
        versions = {SongVersion.MAIN, SongVersion.INSTRUMENTAL}

    project = find_project()

    vocals = next((track for track in project.tracks if track.name == "Vocals"), None)

    did_something = False

    if SongVersion.MAIN in versions:
        did_something = True
        _render_main(project, vocals, verbose)

    if SongVersion.INSTRUMENTAL in versions and vocals:
        did_something = True
        _render_instrumental(versions, project, vocals, vocal_loudness_worth, verbose)

    if SongVersion.ACAPPELLA in versions and vocals:
        did_something = True
        _render_a_cappella(versions, project, vocal_loudness_worth, verbose)

    if not did_something:
        raise click.UsageError("nothing to render")

    # Render causes a project to have unsaved changes, no matter what. Save the user a step.
    project.save()
