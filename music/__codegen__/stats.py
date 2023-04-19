import re
from typing import Dict, Optional


def parse_summary_stats(output: str) -> Dict[str, Optional[float]]:
    max_volume = re.search(r"max_volume: ([\-\d\.]+) dB", output)
    lufs_i = re.search(r"I:\s+([\-\d\.]+) LUFS", output)
    lra = re.search(r"LRA:\s+([\-\d\.]+) LU", output)
    return {
        "max_volume": float(max_volume.group(1)) if max_volume else None,
        "lufs_i": float(lufs_i.group(1)) if lufs_i else None,
        "lra": float(lra.group(1)) if lra else None,
    }
