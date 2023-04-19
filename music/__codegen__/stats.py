# Autogenerated file. Do not modify by hand.
import re
from typing import Dict


def parse_summary_stats(output: str) -> Dict[str, float]:
    """
    Parses max volume, LUFS-I, and LRA from FFmpeg output.

    Args:
        output (str): FFmpeg output.

    Returns:
        Dict[str, float]: A dictionary containing max volume, LUFS-I, and LRA.
    """
    max_volume = re.search(r"max_volume: ([\-\d\.]+) dB", output).group(1)
    lufs_i = re.search(r"I:\s+([\-\d\.]+) LUFS", output).group(1)
    lra = re.search(r"LRA:\s+([\-\d\.]+) LU", output).group(1)
    return {"max_volume": float(max_volume), "lufs_i": float(lufs_i), "lra": float(lra)}
