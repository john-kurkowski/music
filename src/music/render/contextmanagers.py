"""Context managers for before and after Reaper renders."""

import contextlib
import warnings
from collections.abc import Collection, Iterator

from music.util import set_param_value

# Experimentally determined dB scale for Reaper's built-in VST: ReaLimit
LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))


with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


@contextlib.contextmanager
def adjust_master_limiter_threshold(
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
