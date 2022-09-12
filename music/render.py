"""Render vocal and instrumental versions of the current Reaper project."""

import asyncio
import subprocess

import reapy

LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


async def close_dialog() -> None:
    """Reaper's API doesn't expose access to dialogs. Instead, poll for a
    dialog's appearance."""
    while True:
        await asyncio.sleep(2)
        print("current window title:", get_window_title())


def find_master_limiter_threshold(project: reapy.core.Project) -> reapy.core.FXParam:
    """Find the master track's master limiter's threshold parameter."""
    limiters = [fx for fx in project.master_track.fxs[::-1] if "Limit" in fx.name]
    if not limiters:
        raise ValueError("Master limiter not found")
    limiter = limiters[0]

    thresholds = [param for param in limiter.params if "Threshold" in param.name]
    return thresholds[0]


def get_window_title() -> str:
    """TODO"""
    cmd = """
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
        end tell
        tell application frontApp
            if the (count of windows) is not 0 then
                set window_name to name of front window
            end if
        end tell
        return window_name
    """
    cmd = """
    tell application "System Events"
        set myList to name of windows of (processes whose name is "Reaper") -- get a list of lists, each sublist contains names
    end tell
    return myList
    """
    result = subprocess.run(["osascript", "-e", cmd], capture_output=True, check=False)
    return result.stdout.decode("utf-8")


async def render(project: reapy.core.Project) -> None:
    """Render the project. Work around render warning dialogs. Convert sync
    Reaper API to async, while polling for dialogs."""
    loop = asyncio.get_running_loop()
    executor = None
    await asyncio.wait(
        {
            loop.run_in_executor(executor, project.perform_action, RENDER_CMD_ID),
            # asyncio.create_task(close_dialog()),
            asyncio.create_task(close_dialog()),
        },
        return_when=asyncio.FIRST_COMPLETED,
    )


def set_param_value(param: reapy.core.FXParam, value: float) -> None:
    """Set a parameter's value. Work around bug with reapy 0.10's setter."""
    parent_fx = param.parent_list.parent_fx
    parent = parent_fx.parent
    param.functions["SetParamNormalized"](  # type: ignore[operator]
        parent.id, parent_fx.index, param.index, value
    )


def main() -> None:
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

    project.set_info_string("RENDER_PATTERN", "$project")
    asyncio.run(render(project))

    try:
        set_param_value(threshold, threshold_louder_value)
        vocals.mute()
        project.set_info_string("RENDER_PATTERN", "$project (Instrumental)")
        asyncio.run(render(project))
    finally:
        set_param_value(threshold, threshold_previous_value)
        vocals.unmute()
        project.set_info_string("RENDER_PATTERN", "$project")

    project.save()


if __name__ == "__main__":
    main()
