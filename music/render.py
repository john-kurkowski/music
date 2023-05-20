"""Render vocal and instrumental versions of the current Reaper project."""

import enum
import pathlib
import random
import shutil
import subprocess
from collections.abc import Collection

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


def find_acappella_tracks_to_mute(
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


def find_master_limiter_threshold(project: reapy.core.Project) -> reapy.core.FXParam:
    """Find the master track's master limiter's threshold parameter."""
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
    return thresholds[0]


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
    else:
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


def main(  # noqa: C901
    versions: Collection[SongVersion] | None = None,
    vocal_loudness_worth: float = VOCAL_LOUDNESS_WORTH,
    verbose: int = 0,
) -> None:
    """Render the given versions of the current Reaper project."""
    if versions is None:
        versions = {SongVersion.MAIN, SongVersion.INSTRUMENTAL}

    project = find_project()

    threshold = find_master_limiter_threshold(project)
    threshold_previous_value = threshold.normalized
    threshold_louder_value = (
        (threshold_previous_value * LIMITER_RANGE) - vocal_loudness_worth
    ) / LIMITER_RANGE

    vocals = next((track for track in project.tracks if track.name == "Vocals"), None)

    did_something = False

    if SongVersion.MAIN in versions:
        did_something = True
        if vocals:
            vocals.unsolo()
            vocals.unmute()
        out_fil = render_version(project, SongVersion.MAIN)
        print(out_fil)
        print_summary_stats(out_fil, verbose)

    if SongVersion.INSTRUMENTAL in versions and vocals:
        did_something = True

        try:
            set_param_value(threshold, threshold_louder_value)
            vocals.mute()
            out_fil = render_version(project, SongVersion.INSTRUMENTAL)
            if len(versions) > 1:
                print()
            print(out_fil)
            print_summary_stats(out_fil, verbose)
        finally:
            set_param_value(threshold, threshold_previous_value)
            vocals.unmute()

    if SongVersion.ACAPPELLA in versions and vocals:
        did_something = True

        tracks_to_mute = find_acappella_tracks_to_mute(project)
        try:
            set_param_value(threshold, threshold_louder_value)
            for track in tracks_to_mute:
                track.mute()
            out_fil = render_version(project, SongVersion.ACAPPELLA)
            if len(versions) > 1:
                print()
            print(out_fil)
            trim_silence(out_fil)
            print_summary_stats(out_fil, verbose)
        finally:
            set_param_value(threshold, threshold_previous_value)
            for track in tracks_to_mute:
                track.unmute()

    if not did_something:
        raise click.UsageError("nothing to render")

    # Render causes a project to have unsaved changes, no matter what. Save the user a step.
    project.save()


class FeatureUnavailableError(RuntimeError):
    """Raised when a feature is unavailable, e.g. due to missing dependencies."""


if __name__ == "__main__":
    main()
