"""Read audio duration and cumulative measurements through FFprobe JSON."""

import json
import math
import subprocess
from pathlib import Path


def duration_for_file(fil: Path) -> float:
    """Return container duration in seconds, treating N/A as zero."""
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-i",
            fil,
            "-show_entries",
            "format=duration",
            "-of",
            "json",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    duration = json.loads(proc.stdout).get("format", {}).get("duration")
    if duration is None:
        raise ValueError(f"Could not find audio duration in ffprobe output: {fil}")
    return 0.0 if duration == "N/A" else float(duration)


def summary_stats_for_file(fil: Path, *, verbose: int = 0) -> dict[str, float | str]:
    """Return duration (HH:MM:SS.xx), peak (dB), integrated LUFS, and LRA (LU)."""
    centiseconds = int(duration_for_file(fil) * 100 + 0.5)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, fraction = divmod(remainder, 100)
    # Inherit the input descriptor so arbitrary filenames never enter filter syntax.
    with fil.open("rb") as audio:
        graph = (
            f"amovie=/dev/fd/{audio.fileno()},aformat=sample_fmts=s16,"
            "astats=metadata=1:measure_perchannel=none:measure_overall=Max_level+Min_level,"
            "ebur128=metadata=1"
        )
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                graph,
                "-show_entries",
                "frame_tags=lavfi.astats.Overall.Max_level,lavfi.astats.Overall.Min_level,lavfi.r128.I,lavfi.r128.LRA",
                "-of",
                "json",
            ],
            capture_output=True,
            check=True,
            text=True,
            pass_fds=(audio.fileno(),),
        )
    return parse_summary_stats(
        proc.stdout, f"{hours:02}:{minutes:02}:{seconds:02}.{fraction:02}"
    )


def parse_summary_stats(output: str, duration: str) -> dict[str, float | str]:
    """Read cumulative frame tags, preserving FFmpeg's one-decimal summaries."""
    tags: dict[str, str] = {}
    for frame in json.loads(output)["frames"]:
        # A partial final frame has peak tags but no updated ebur128 measurements.
        tags.update(frame.get("tags", {}))
    result: dict[str, float | str] = {"duration": duration}
    if tags:
        peak = max(
            abs(float(tags[f"lavfi.astats.Overall.{key}"]))
            for key in ("Min_level", "Max_level")
        )
        # volumedetect uses signed 16-bit amplitudes and reports -91 dB for silence.
        result["max_volume"] = (
            round(20 * math.log10(peak / 32768), 1) if peak else -91.0
        )
        result["lufs_i"] = round(float(tags.get("lavfi.r128.I", "-70")), 1)
        result["lra"] = round(float(tags.get("lavfi.r128.LRA", "0")), 1)
    return result
