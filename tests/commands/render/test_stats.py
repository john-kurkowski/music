"""Tests for the application's structured audio statistics contract."""

import json
import shutil
import struct
import wave
from pathlib import Path
from subprocess import CalledProcessError
from unittest import mock

import pytest

from music.commands.render.stats import parse_summary_stats, summary_stats_for_file

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "name, expected",
    [
        (
            "tone",
            {
                "duration": "00:00:02.00",
                "max_volume": -18.1,
                "lufs_i": -21.1,
                "lra": 0.0,
            },
        ),
        (
            "silence",
            {
                "duration": "00:00:02.00",
                "max_volume": -91.0,
                "lufs_i": -70.0,
                "lra": 0.0,
            },
        ),
    ],
)
def test_captured_summary(name: str, expected: dict[str, float | str]) -> None:
    """Preserve known statistics using captured structured measurements."""
    assert (
        parse_summary_stats((_FIXTURES / f"{name}.json").read_text(), "00:00:02.00")
        == expected
    )


def test_partial_final_frame() -> None:
    """Retain loudness while picking up a peak in the partial final frame."""
    output = json.dumps(
        {
            "frames": [
                {
                    "tags": {
                        "lavfi.r128.I": "-14.234",
                        "lavfi.r128.LRA": "4.567",
                        "lavfi.astats.Overall.Min_level": "-4096",
                        "lavfi.astats.Overall.Max_level": "4096",
                    }
                },
                {
                    "tags": {
                        "lavfi.astats.Overall.Min_level": "-16384",
                        "lavfi.astats.Overall.Max_level": "8192",
                    }
                },
            ]
        }
    )
    assert parse_summary_stats(output, "00:00:00.25") == {
        "duration": "00:00:00.25",
        "max_volume": -6.0,
        "lufs_i": -14.2,
        "lra": 4.6,
    }


def test_empty_audio() -> None:
    """Omit measurements when no frames were decoded."""
    assert parse_summary_stats('{"frames": []}', "00:00:00.00") == {
        "duration": "00:00:00.00"
    }


def test_stats_for_file(subprocess: mock.Mock, tmp_path: Path) -> None:
    """Combine container duration and frame metadata at the file boundary."""
    audio = tmp_path / "tone.wav"
    audio.touch()
    subprocess.side_effect = [
        mock.Mock(stdout='{"format": {"duration": "2"}}'),
        mock.Mock(stdout=(_FIXTURES / "tone.json").read_text()),
    ]
    assert summary_stats_for_file(audio) == {
        "duration": "00:00:02.00",
        "max_volume": -18.1,
        "lufs_i": -21.1,
        "lra": 0.0,
    }


def test_duration_display_carry(subprocess: mock.Mock, tmp_path: Path) -> None:
    """Round duration to centiseconds before splitting clock fields."""
    audio = tmp_path / "tone.wav"
    audio.touch()
    subprocess.side_effect = [
        mock.Mock(stdout='{"format": {"duration": "3599.999"}}'),
        mock.Mock(stdout='{"frames": []}'),
    ]
    assert summary_stats_for_file(audio) == {"duration": "01:00:00.00"}


def test_stats_process_failure(subprocess: mock.Mock) -> None:
    """Propagate analysis failures rather than reporting empty statistics."""
    subprocess.side_effect = CalledProcessError(1, "ffprobe")
    with pytest.raises(CalledProcessError):
        summary_stats_for_file(Path("broken.wav"))


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="FFprobe is unavailable")
@pytest.mark.parametrize(
    "length, expected",
    [
        (
            220,
            {
                "duration": "00:00:00.00",
                "max_volume": -6.0,
                "lufs_i": -70.0,
                "lra": 0.0,
            },
        ),
        (
            11025,
            {
                "duration": "00:00:00.25",
                "max_volume": -6.0,
                "lufs_i": -70.0,
                "lra": 0.0,
            },
        ),
    ],
)
def test_live_tail_peak_and_filename(
    tmp_path: Path, length: int, expected: dict[str, float | str]
) -> None:
    """Analyze short inputs and final-frame peaks through arbitrary filenames."""
    audio = tmp_path / "audio '[],:\\.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(44100)
        output.writeframes(b"\x00\x00" * (length - 1) + struct.pack("<h", -16384))
    assert summary_stats_for_file(audio) == expected
