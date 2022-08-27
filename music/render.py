"""Render vocal and instrumental versions of the current Reaper project."""

from dataclasses import dataclass
import sys

sys.path.append("/Applications/REAPER.app/Contents/Plugins/")

# pylint: disable-next=import-error,wrong-import-position
import reaper_python  # type: ignore[import] # noqa: E402

# Bogus buffer values to send to Reaper's C API. Python doesn't use buffers.
BUF = ""
BUF_SIZE = 2048

PROJECT_ID = 0

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


@dataclass
class ReaperParam:
    """A getter/setter for a parameter in Reaper. Wraps Reaper's un-Pythonic API."""

    track: object
    fx_i: int
    param_i: int

    @property
    def name(self) -> str:
        """The name of this param."""
        value_idx = 4
        return reaper_python.RPR_TrackFX_GetParamName(
            self.track, self.fx_i, self.param_i, BUF, BUF_SIZE
        )[value_idx]

    @property
    def value(self) -> float:
        """The value of this param."""
        return reaper_python.RPR_TrackFX_GetParamNormalized(
            self.track, self.fx_i, self.param_i
        )

    @value.setter
    def value(self, value: float) -> None:
        return reaper_python.RPR_TrackFX_SetParamNormalized(
            self.track, self.fx_i, self.param_i, value
        )

    def __str__(self) -> str:
        return f"{self.name}={self.value}"


def find_master_limiter_threshold() -> ReaperParam:
    """Find the master track's master limiter's threshold parameter."""
    master_track = reaper_python.RPR_GetMasterTrack(PROJECT_ID)
    fx_count = reaper_python.RPR_TrackFX_GetCount(master_track)
    value_idx = 3
    fx_names = [
        reaper_python.RPR_TrackFX_GetFXName(master_track, i, BUF, BUF_SIZE)[value_idx]
        for i in range(0, fx_count)
    ]
    limiters = [
        i for (i, name) in reversed(list(enumerate(fx_names))) if "Limit" in name
    ]
    if not limiters:
        raise ValueError("Master limiter not found")
    fx_i = limiters[0]

    param_count = reaper_python.RPR_TrackFX_GetNumParams(master_track, fx_i)
    value_idx = 4
    params = [
        ReaperParam(master_track, fx_i, param_i) for param_i in range(0, param_count)
    ]
    thresholds = [param for param in params if "Threshold" in param.name]
    return thresholds[0]


def main() -> None:
    """Module entrypoint."""
    is_set = True

    threshold = find_master_limiter_threshold()

    # Can't seem to programmatically set "Silently increment filenames to avoid
    # overwriting." That would be nice so the user doesn't have to (wait to)
    # interact with GUI elements at all.
    #
    # reaper_python.RPR_GetSetProjectInfo(PROJECT_ID, "RENDER_ADDTOPROJ", 16, is_set)

    reaper_python.RPR_GetSetProjectInfo_String(
        PROJECT_ID, "RENDER_PATTERN", "$project", is_set
    )

    flags = 0
    reaper_python.RPR_Main_OnCommand(RENDER_CMD_ID, flags)

    # TODO: need to mute vocals and set e.g. -7.0db threshold to -9.0db. Then
    #       unmute vocals and restore threshold. Example thresholds:
    #
    #       0.7361111044883728
    #       0.7083333134651184

    threshold_previous_value = threshold.value

    try:
        threshold.value = 0.0
        reaper_python.RPR_GetSetProjectInfo_String(
            PROJECT_ID, "RENDER_PATTERN", "$project (Instrumental)", is_set
        )
        reaper_python.RPR_Main_OnCommand(RENDER_CMD_ID, flags)
    finally:
        threshold.value = threshold_previous_value
        reaper_python.RPR_GetSetProjectInfo_String(
            PROJECT_ID, "RENDER_PATTERN", "$project", is_set
        )


if __name__ == "__main__":
    main()
