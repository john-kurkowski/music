"""Parse FFmpeg audio statistics into the application's summary fields."""

import re

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+|inf)"


def parse_summary_stats(output: str) -> dict[str, float | str]:
    """Return available duration, peak volume, integrated loudness, and range.

    Duration remains FFmpeg's HH:MM:SS.xx string; max_volume is dB,
    lufs_i is LUFS, and lra is LU. Missing measurements are omitted.
    Only the final ebur128 summary supplies loudness measurements: frame
    logs and the filter's initial empty summary are not final results.
    """
    result: dict[str, float | str] = {}
    duration = re.search(r"Duration:\s*(\d+:\d+:\d+\.\d+)", output)
    if duration:
        result["duration"] = duration.group(1)

    peak = re.search(rf"max_volume:\s*({_NUMBER})\s+dB", output)
    if peak:
        result["max_volume"] = float(peak.group(1))

    summaries = list(re.finditer(r"\[Parsed_ebur128_[^\]]+\]\s+Summary:", output))
    if summaries:
        summary = output[summaries[-1].end() :]
        for key, label, unit in (("lufs_i", "I", "LUFS"), ("lra", "LRA", "LU")):
            match = re.search(
                rf"^\s*{label}:\s*({_NUMBER})\s+{unit}\s*$", summary, re.MULTILINE
            )
            if match:
                result[key] = float(match.group(1))
    return result
