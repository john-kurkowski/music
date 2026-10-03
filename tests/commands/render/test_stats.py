"""Tests for the application's FFmpeg statistics contract."""

from pathlib import Path
from subprocess import CalledProcessError
from unittest import mock

import pytest

from music.commands.render.result import summary_stats_for_file
from music.commands.render.stats import parse_summary_stats

_FIXTURES = Path(__file__).parent / "fixtures"


def test_tone_summary() -> None:
    """Parse final measurements from a captured tone analysis."""
    assert parse_summary_stats((_FIXTURES / "tone.txt").read_text()) == {
        "duration": "00:00:02.00",
        "max_volume": -18.1,
        "lufs_i": -21.1,
        "lra": 0.0,
    }


def test_silence_summary() -> None:
    """Preserve FFmpeg's finite silence floor without inventing infinity."""
    assert parse_summary_stats((_FIXTURES / "silence.txt").read_text()) == {
        "duration": "00:00:02.00",
        "max_volume": -91.0,
        "lufs_i": -70.0,
        "lra": 0.0,
    }


def test_final_summary_overrides_initial_and_frame_measurements() -> None:
    """Use the final summary rather than initialization or per-frame values."""
    output = """[Parsed_ebur128_1 @ 0x1] Summary:
  I: -70.0 LUFS
  LRA: 0.0 LU
[Parsed_ebur128_1 @ 0x1] t: 1.0 I: -30.0 LUFS LRA: 1.0 LU
[Parsed_ebur128_1 @ 0x2] Summary:
  I: -14.2 LUFS
  LRA: 4.5 LU
"""
    assert parse_summary_stats(output) == {"lufs_i": -14.2, "lra": 4.5}


def test_missing_measurements() -> None:
    """Omit unavailable duration and unrecognized measurements."""
    assert parse_summary_stats("Duration: N/A\nI: -30.0 LUFS\nLRA: 2.0 LU") == {}


def test_partial_final_summary() -> None:
    """Do not reuse a missing measurement from an earlier summary."""
    assert parse_summary_stats("""[Parsed_ebur128_1 @ 0x1] Summary:
  I: -70.0 LUFS
  LRA: 0.0 LU
[Parsed_ebur128_1 @ 0x2] Summary:
  I: -14.2 LUFS
""") == {"lufs_i": -14.2}


def test_numeric_boundaries() -> None:
    """Accept integer, signed, and infinite measurements with whitespace."""
    assert parse_summary_stats("""Duration: 123:45:06.789
max_volume: -inf dB
[Parsed_ebur128_1 @ 0x2] Summary:
  I: +1 LUFS
  LRA: 12 LU
""") == {
        "duration": "123:45:06.789",
        "max_volume": float("-inf"),
        "lufs_i": 1.0,
        "lra": 12.0,
    }


def test_stats_for_file(subprocess: mock.Mock) -> None:
    """Pass captured stderr through the adapter at the application boundary."""
    subprocess.return_value.stderr = (_FIXTURES / "tone.txt").read_text()
    assert summary_stats_for_file(Path("tone.wav")) == {
        "duration": "00:00:02.00",
        "max_volume": -18.1,
        "lufs_i": -21.1,
        "lra": 0.0,
    }


def test_stats_process_failure(subprocess: mock.Mock) -> None:
    """Propagate analysis failures rather than reporting empty statistics."""
    subprocess.side_effect = CalledProcessError(1, "ffmpeg")
    with pytest.raises(CalledProcessError):
        summary_stats_for_file(Path("broken.wav"))
