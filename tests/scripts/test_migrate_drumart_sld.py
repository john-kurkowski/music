"""Tests for Drumart SLD migration tooling."""

from __future__ import annotations

import io
import struct
import wave
import zipfile
from pathlib import Path

import pytest

from scripts import migrate_drumart_sld


def test_parse_kit_extracts_embedded_pcm_records() -> None:
    """Decode sample metadata and PCM bytes from Drumart bank records."""
    pcm = _pcm(1, -2, 3, -4, 5, -6)
    kit = migrate_drumart_sld.parse_kit_bytes(
        _bank_record("PRESET (1).flac", frames=3, pcm=pcm),
        label="[SLD] Tiny",
        bank_file=Path("[SLD] Tiny.mse"),
    )

    assert len(kit.samples) == 1
    sample = kit.samples[0]
    assert sample.slot == 0
    assert sample.channels == 2
    assert sample.sample_rate == 44100
    assert sample.frames == 3
    assert sample.pcm == pcm


def test_wav_bytes_preserve_audio_shape_and_values() -> None:
    """Write extracted PCM as ordinary WAV audio."""
    pcm = _pcm(100, -100, 200, -200)
    sample = migrate_drumart_sld.DrumartSample(
        slot=0,
        source_path="PRESET (1).flac",
        channels=2,
        sample_rate=44100,
        frames=2,
        pcm=pcm,
    )

    with wave.open(io.BytesIO(migrate_drumart_sld.wav_bytes(sample)), "rb") as wav:
        assert wav.getnchannels() == 2
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 44100
        assert wav.getnframes() == 2
        assert wav.readframes(2) == pcm


def test_write_kit_creates_sitala_zip_and_canonical_samples(tmp_path: Path) -> None:
    """Create bundled Sitala kits and Dropbox sample copies."""
    kit = migrate_drumart_sld.parse_kit_bytes(
        _bank_record("PRESET (1).flac", frames=1, pcm=_pcm(7, -7)),
        label="[SLD] Tiny",
        bank_file=Path("[SLD] Tiny.mse"),
    )
    samples_dir = tmp_path / "samples"
    kits_dir = tmp_path / "kits"

    migrate_drumart_sld.write_kit(kit, samples_dir=samples_dir, kits_dir=kits_dir)

    canonical_sample = samples_dir / "[SLD] Tiny" / "01 - Pad 1.wav"
    assert canonical_sample.is_file()

    sitala_file = kits_dir / "[SLD] Tiny.sitala"
    with zipfile.ZipFile(sitala_file) as archive:
        assert sorted(archive.namelist()) == ["Samples/01 - Pad 1.wav", "kit1.xml"]
        assert archive.read("Samples/01 - Pad 1.wav") == canonical_sample.read_bytes()
        kit_xml = archive.read("kit1.xml").decode()

    assert '<kit label="[SLD] Tiny">' in kit_xml
    assert 'sampleEnd="1"' in kit_xml
    assert 'internal="Samples/01 - Pad 1.wav"' in kit_xml


def test_dry_run_does_not_create_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Report planned work without writing files by default."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "[SLD] Tiny.mse").write_bytes(
        _bank_record("PRESET (1).flac", frames=1, pcm=_pcm(1, -1))
    )
    samples_dir = tmp_path / "samples"
    kits_dir = tmp_path / "kits"

    migrate_drumart_sld.main(
        [
            "--source",
            str(source),
            "--samples-dir",
            str(samples_dir),
            "--kits-dir",
            str(kits_dir),
            "--only",
            "[SLD] Tiny",
        ]
    )

    assert "[SLD] Tiny: 1 samples" in capsys.readouterr().out
    assert not samples_dir.exists()
    assert not kits_dir.exists()


def _bank_record(filename: str, *, frames: int, pcm: bytes) -> bytes:
    path = f"..\\..\\SAMPLES\\FINAL PRESETS\\SLD\\PRESET\\{filename}".encode()
    return (
        b"MSE \x02\x01header\x00"
        + path
        + b"\x00"
        + struct.pack("<5I", 2, 44100, 2, 123, frames)
        + pcm
    )


def _pcm(*values: int) -> bytes:
    return struct.pack(f"<{len(values)}h", *values)
