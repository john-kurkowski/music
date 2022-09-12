"""Render vocal and instrumental versions of the current Reaper project."""

import collections
import enum
import pathlib
import random
import shutil

import reapy

LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

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
        (threshold_previous_value * LIMITER_RANGE) - 2.0
    ) / LIMITER_RANGE

    vocals = [track for track in project.tracks if track.name == "Vocals"][0]

    project_name = pathlib.Path(project.name).stem
    # Avoid "Overwrite" "Render Warning" dialog, which can't be scripted, with a temporary filename
    rand_id = random.randrange(10**5, 10**6)
    main_name = f"{project_name} {rand_id}.tmp"
    instrumental_name = f"{project_name} (Instrumental) {rand_id}.tmp"

    if SongVersion.MAIN in versions:
        project.set_info_string("RENDER_PATTERN", main_name)
        project.perform_action(RENDER_CMD_ID)

    try:
        if SongVersion.INSTRUMENTAL in versions:
            try:
                set_param_value(threshold, threshold_louder_value)
                vocals.mute()
                project.set_info_string("RENDER_PATTERN", instrumental_name)
                project.perform_action(RENDER_CMD_ID)
            finally:
                set_param_value(threshold, threshold_previous_value)
                vocals.unmute()
    finally:
        project.set_info_string("RENDER_PATTERN", "$project")

    out_dir = pathlib.Path(project.path)
    if SongVersion.MAIN in versions:
        shutil.move(out_dir / f"{main_name}.wav", out_dir / f"{project_name}.wav")
    if SongVersion.INSTRUMENTAL in versions:
        shutil.move(
            out_dir / f"{instrumental_name}.wav",
            out_dir / f"{project_name} (Instrumental).wav",
        )

    project.save()


if __name__ == "__main__":
    main()
