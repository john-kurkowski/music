"""Context managers for before and after Reaper renders."""

import contextlib
import warnings
from collections.abc import Callable, Collection, Iterator
from functools import partial
from pathlib import Path
from typing import TypeVar, cast

from music.util import ExtendedProject, SongVersion, set_param_value

from .consts import (
    LIMITER_RANGE,
    MONO_TRACKS_TO_MONO_FILES,
    SELECTED_TRACKS_VIA_MASTER,
    SWS_ERROR_SENTINEL,
)

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


T = TypeVar("T")


def adjust_master_limiter_threshold(
    project: reapy.core.Project, vocal_loudness_worth: float
) -> contextlib.AbstractContextManager[None]:
    """Find the `project` master track's master limiter's threshold parameter and adjust its value without the vocal, then restore the original value."""
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

    return get_set_restore(
        lambda: threshold_previous_value,
        partial(set_param_value, threshold),
        threshold_louder_value,
    )


def adjust_render_pattern(
    project: ExtendedProject, pattern: Path
) -> contextlib.AbstractContextManager[None]:
    """Set the `project` RENDER_PATTERN, then restore the original value."""
    return get_set_restore(
        partial(project.get_info_string, "RENDER_PATTERN"),
        partial(project.set_info_string, "RENDER_PATTERN"),
        str(pattern),
    )


def adjust_render_settings(
    project: ExtendedProject, version: SongVersion
) -> contextlib.AbstractContextManager[None]:
    """Set the `project` RENDER_SETTINGS according to `version`, then restore the original value.

    This only changes anything for rendering stems. There are several Reaper
    render presets for stems. The best one I've found for my conventions is
    selecting tracks (elsewhere in this folder) and processing them through the
    master track. While there, as a slight time and space efficiency, keep mono
    files in mono.
    """
    if version != SongVersion.STEMS:
        return contextlib.nullcontext()

    render_settings = MONO_TRACKS_TO_MONO_FILES | SELECTED_TRACKS_VIA_MASTER

    return get_set_restore(
        partial(project.get_info_value, "RENDER_SETTINGS"),
        partial(
            project.set_info_value,
            "RENDER_SETTINGS",
        ),
        cast(float, render_settings),
    )


@contextlib.contextmanager
def avoid_fx_tails() -> Iterator[None]:
    """Change global settings to avoid FX tails at the beginning of the render, then restore the global settings' original values."""
    off = 0

    with (
        get_set_restore(
            partial(
                reapy.reascript_api.SNM_GetIntConfigVar,  # type: ignore[attr-defined]
                "runallonstop",
                SWS_ERROR_SENTINEL,
            ),
            partial(reapy.reascript_api.SNM_SetIntConfigVar, "runallonstop"),  # type: ignore[attr-defined]
            off,
        ),
        get_set_restore(
            partial(
                reapy.reascript_api.SNM_GetIntConfigVar,  # type: ignore[attr-defined]
                "runafterstop",
                SWS_ERROR_SENTINEL,
            ),
            partial(reapy.reascript_api.SNM_SetIntConfigVar, "runafterstop"),  # type: ignore[attr-defined]
            off,
        ),
    ):
        yield


@contextlib.contextmanager
def get_set_restore(
    getter: Callable[[], T], setter: Callable[[T], None], during_value: T
) -> Iterator[None]:
    """Get the previous value from `getter`, set `during_value` with the `setter`, then restore the original value."""
    prev_value = getter()
    try:
        setter(during_value)
        yield
    finally:
        setter(prev_value)


@contextlib.contextmanager
def mute_tracks(tracks: Collection[reapy.core.Track]) -> Iterator[None]:
    """Mute all tracks in the given collection, then unmute them."""
    for track in tracks:
        track.mute()
    yield
    for track in tracks:
        track.unmute()


@contextlib.contextmanager
def toggle_fx_for_tracks(
    tracks: Collection[reapy.core.Track], is_enabled: bool
) -> Iterator[None]:
    """Toggle all effects in the given collection of tracks, then toggle them back."""
    fxs = [
        fx
        for track in tracks
        for i in range(len(track.fxs))
        if (fx := track.fxs[i]) and fx.is_enabled != is_enabled
    ]
    for fx in fxs:
        fx.is_enabled = is_enabled
    yield
    for fx in fxs:
        fx.is_enabled = not is_enabled
