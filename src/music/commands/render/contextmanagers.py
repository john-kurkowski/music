"""Context managers for before and after Reaper renders."""

import contextlib
import warnings
from collections.abc import Callable, Collection, Iterator
from functools import partial
from pathlib import Path
from typing import TypeVar, cast

from music.utils.fx import set_param_value
from music.utils.project import ExtendedProject

from .consts import (
    LIMITER_RANGE,
    SWS_ERROR_SENTINEL,
)
from .tracks import is_muted

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


T = TypeVar("T")


def adjust_master_limiter_threshold(
    project: reapy.core.Project, vocal_loudness_worth: float
) -> contextlib.AbstractContextManager[None]:
    """Find the `project` master track's master limiter's threshold parameter and adjust its value without the vocal, then restore the original value."""
    if vocal_loudness_worth == 0.0:
        return contextlib.nullcontext()

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


@contextlib.contextmanager
def adjust_render_bounds(project: ExtendedProject) -> Iterator[None]:
    """Set `project` render bounds, then restore the original values.

    This sets the render start and end times to contain all unmuted media
    items. Different song versions may therefore have different starts and ends
    and durations. This is more flexible than a human remembering to set fixed,
    custom times in the Reaper GUI, per song version.
    """
    custom_time_bounds = 0

    with reapy.inside_reaper():
        items = sorted(
            (
                item
                for track in project.tracks
                if not is_muted(track)
                for item in track.items
                if not item.get_info_value("B_MUTE_ACTUAL")
            ),
            key=lambda item: item.position,
        )

    startpos = items[0].position if items else 0.0
    endpos = max(
        (item.position + item.length for item in items),
        default=0.0,
    )

    with (
        get_set_restore(
            partial(project.get_info_value, "RENDER_BOUNDSFLAG"),
            partial(project.set_info_value, "RENDER_BOUNDSFLAG"),
            cast(float, custom_time_bounds),
        ),
        get_set_restore(
            partial(project.get_info_value, "RENDER_STARTPOS"),
            partial(project.set_info_value, "RENDER_STARTPOS"),
            startpos,
        ),
        get_set_restore(
            partial(project.get_info_value, "RENDER_ENDPOS"),
            partial(project.set_info_value, "RENDER_ENDPOS"),
            endpos,
        ),
    ):
        yield


@contextlib.contextmanager
def avoid_fx_tails(project: ExtendedProject) -> Iterator[None]:
    """Change global settings to avoid FX tails at the beginning of the render, then restore the global settings' original values."""
    off = 0
    start_time = 0.0

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
        get_set_restore(
            partial(getattr, project, "cursor_position"),
            partial(setattr, project, "cursor_position"),
            start_time,
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
    try:
        yield
    finally:
        for track in tracks:
            track.unmute()


@contextlib.contextmanager
def select_tracks_only(
    project: ExtendedProject, tracks: Collection[reapy.core.Track]
) -> Iterator[None]:
    """Select only the tracks in the given collection, unselecting all other tracks, then restore track selection."""
    tracks_to_select = {track.id: track for track in tracks}

    with reapy.inside_reaper():
        original_selection = {track.id: track.is_selected for track in project.tracks}

        for track in project.tracks:
            should_be_selected = track.id in tracks_to_select
            if track.is_selected != should_be_selected:
                if should_be_selected:
                    track.select()
                else:
                    track.unselect()

    try:
        yield
    finally:
        with reapy.inside_reaper():
            for track in project.tracks:
                if track.is_selected != original_selection[track.id]:
                    if original_selection[track.id]:
                        track.select()
                    else:
                        track.unselect()


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

    try:
        yield
    finally:
        for fx in fxs:
            fx.is_enabled = not is_enabled
