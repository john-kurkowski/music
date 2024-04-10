"""Reaper render constants."""

# Experimentally determined dB scale for Reaper's built-in VST: ReaLimit
LIMITER_RANGE = sum(abs(point) for point in (-60.0, 12.0))

# RENDER_SETTINGS bit flags
MONO_TRACKS_TO_MONO_FILES = 16
SELECTED_TRACKS_VIA_MASTER = 128

# The typical loudness of vocals, in dBs, relative to the instrumental
VOCAL_LOUDNESS_WORTH = 2.0

# Common error code found in SWS functions source
SWS_ERROR_SENTINEL = -666
