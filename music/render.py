"""Render vocal and instrumental versions of the current Reaper project."""

import reapy

LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


def find_master_limiter_threshold(project: reapy.core.Project) -> reapy.core.FXParam:
    """Find the master track's master limiter's threshold parameter."""
    limiters = [fx for fx in project.master_track.fxs[::-1] if "Limit" in fx.name]
    if not limiters:
        raise ValueError("Master limiter not found")
    limiter = limiters[0]

    thresholds = [param for param in limiter.params if "Threshold" in param.name]
    return thresholds[0]


def set_param_value(param: reapy.core.FXParam, value: float) -> None:
    """Work around bug with reapy's setter in 0.10."""
    parent_fx = param.parent_list.parent_fx
    parent = parent_fx.parent
    param.functions["SetParamNormalized"](  # type: ignore[operator]
        parent.id, parent_fx.index, param.index, value
    )


def main() -> None:
    """Module entrypoint."""
    project = reapy.Project()

    threshold = find_master_limiter_threshold(project)

    # Can't seem to programmatically set "Silently increment filenames to avoid
    # overwriting." That would be nice so the user doesn't have to (wait to)
    # interact with GUI elements at all.
    #
    # reaper_python.RPR_GetSetProjectInfo(PROJECT_ID, "RENDER_ADDTOPROJ", 16, is_set)

    project.set_info_string("RENDER_PATTERN", "$project")
    project.perform_action(RENDER_CMD_ID)

    # TODO: mute vocals

    threshold_previous_value = threshold.normalized
    threshold_louder_value = (
        (threshold_previous_value * LIMITER_RANGE) - 2.0
    ) / LIMITER_RANGE

    try:
        set_param_value(threshold, threshold_louder_value)
        project.set_info_string("RENDER_PATTERN", "$project (Instrumental)")
        project.perform_action(RENDER_CMD_ID)
    finally:
        set_param_value(threshold, threshold_previous_value)
        project.set_info_string("RENDER_PATTERN", "$project")


if __name__ == "__main__":
    main()
