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
    yield
    for track in tracks:
        track.unmute()


@contextlib.contextmanager
def normalize_tempo(project: ExtendedProject) -> Iterator[None]:
    """Normalize the tempo of the project to a single tempo, then restore the project's custom tempo markers.

    Assumes the "normal" tempo of the project is whatever singular tempo is set
    in the project's settings. Does not inspect the marker values themselves.

    Saves the master track tempo envelope data to project's external state
    storage (vs. relying on this Python program's memory), deletes the markers,
    then sets the markers back.

    H/T https://forum.cockos.com/showpost.php?p=1992179&postcount=12
    """
    tempo_envelope = project.master_track.envelopes[0]
    is_undo_optional = False
    success, _, envelope_chunk, *_ = reapy.RPR.GetEnvelopeStateChunk(  # type: ignore[attr-defined]
        tempo_envelope.id, "", 999, is_undo_optional
    )
    assert success, "GetEnvelopeStateChunk failed"
    reapy.RPR.SetProjExtState(  # type: ignore[attr-defined]
        project.id, "MPL_TOGGLETEMPOENV", "temptimesignenv", envelope_chunk
    )

    num_markers = project.n_tempo_markers
    for i in range(num_markers):
        reapy.RPR.DeleteTempoTimeSigMarker(project.id, num_markers - i - 1)  # type: ignore[attr-defined]

    yield

    success, _, _, _, ext_envelope_chunk, *_ = reapy.RPR.GetProjExtState(  # type: ignore[attr-defined]
        project.id, "MPL_TOGGLETEMPOENV", "temptimesignenv", "", 999
    )
    assert success, "GetProjExtState failed"
    reapy.RPR.SetEnvelopeStateChunk(  # type: ignore[attr-defined]
        tempo_envelope.id, ext_envelope_chunk, is_undo_optional
    )

    # TODO: why does the Lua version set only the last marker? What if I don't do this?

    (
        _,
        _,
        _,
        timepos,
        measurepos,
        beatpos,
        bpm,
        timesig_num,
        timesig_denom,
        lineartempo,
    ) = reapy.RPR.GetTempoTimeSigMarker(  # type: ignore[attr-defined]
        project.id,
        project.n_tempo_markers - 1,
        999.9,
        999,
        999.9,
        999.9,
        999,
        999,
        False,
    )

    reapy.RPR.SetTempoTimeSigMarker(  # type: ignore[attr-defined]
        project.id,
        project.n_tempo_markers - 1,
        timepos,
        measurepos,
        beatpos,
        bpm,
        timesig_num,
        timesig_denom,
        lineartempo,
    )

    reapy.RPR.UpdateTimeline()  # type: ignore[attr-defined]


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
