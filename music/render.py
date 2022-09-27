"""Render vocal and instrumental versions of the current Reaper project."""

import collections
import enum
import pathlib
import random
import shutil
import subprocess
from typing import Sequence, Union

import reapy

from .util import assert_exhaustiveness

LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

VOCAL_LOUDNESS_WORTH = 2.0

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


class SongVersion(enum.Enum):
    """Different versions of a song to render."""

    MAIN = enum.auto()
    INSTRUMENTAL = enum.auto()


def find_master_limiter_threshold(project: reapy.core.Project) -> reapy.core.FXParam:
    """Find the master track's master limiter's threshold parameter."""
    limiters = [fx for fx in project.master_track.fxs[::-1] if "Limit" in fx.name]
    if not limiters:
        raise ValueError("Master limiter not found")
    limiter = limiters[0]

    thresholds = [param for param in limiter.params if "Threshold" in param.name]
    return thresholds[0]


def log_summary_stats(fil: pathlib.Path) -> None:
    """Log statistics for the given audio file, like LUFS-I and LRA."""
    cmd: Sequence[Union[str, pathlib.Path]] = [
        "ffmpeg",
        "-i",
        fil,
        "-filter:a",
        ",".join(("volumedetect", "ebur128=framelog=verbose")),
        "-f",
        "null",
        "/dev/null",
    ]
    with subprocess.Popen(cmd):
        pass


def render_version(project: reapy.core.Project, version: SongVersion) -> None:
    """Trigger Reaper to render the current project audio. Name the output file
    according to the given version."""
    project_name = pathlib.Path(project.name).stem
    if version is SongVersion.MAIN:
        out_name = project_name
    elif version is SongVersion.INSTRUMENTAL:
        out_name = f"{project_name} (Instrumental)"
    else:
        assert_exhaustiveness(version)

    # Avoid "Overwrite" "Render Warning" dialog, which can't be scripted, with a temporary filename
    rand_id = random.randrange(10**5, 10**6)
    in_name = f"{out_name} {rand_id}.tmp"

    project.set_info_string("RENDER_PATTERN", in_name)
    project.perform_action(RENDER_CMD_ID)

    out_dir = pathlib.Path(project.path)
    out_fil = out_dir / f"{out_name}.wav"
    shutil.move(out_dir / f"{in_name}.wav", out_fil)

    log_summary_stats(out_fil)


def set_param_value(param: reapy.core.FXParam, value: float) -> None:
    """Set a parameter's value. Work around bug with reapy 0.10's setter."""
    parent_fx = param.parent_list.parent_fx
    parent = parent_fx.parent
    param.functions["SetParamNormalized"](  # type: ignore[operator]
        parent.id, parent_fx.index, param.index, value
    )


def main(
    versions: collections.abc.Collection[SongVersion] = frozenset(
        (SongVersion.MAIN, SongVersion.INSTRUMENTAL)
    )
) -> None:
    """Module entrypoint."""
    try:
        project = reapy.Project()
    except AttributeError as aterr:
        if "module" in str(aterr) and "reascript_api" in str(aterr):
            raise Exception(
                "Error while loading Reaper project. Is Reaper running?"
            ) from aterr

    threshold = find_master_limiter_threshold(project)
    threshold_previous_value = threshold.normalized
    threshold_louder_value = (
        (threshold_previous_value * LIMITER_RANGE) - VOCAL_LOUDNESS_WORTH
    ) / LIMITER_RANGE

    vocals = [track for track in project.tracks if track.name == "Vocals"][0]

    if SongVersion.MAIN in versions:
        render_version(project, SongVersion.MAIN)

    try:
        if SongVersion.INSTRUMENTAL in versions:
            try:
                set_param_value(threshold, threshold_louder_value)
                vocals.mute()
                render_version(project, SongVersion.INSTRUMENTAL)
            finally:
                set_param_value(threshold, threshold_previous_value)
                vocals.unmute()
    finally:
        project.set_info_string("RENDER_PATTERN", "$project")

    # Render causes a project to have unsaved changes, no matter what. Save the user a step.
    project.save()


if __name__ == "__main__":
    main()
