"""Extract Drumart SLD sample banks into portable WAVs and Sitala kits.

Drumart SLD is a Maize Sampler-based instrument whose factory presets are
stored as `.mse` banks. The extracted WAVs are the portable source of truth for
project archives; generated `.sitala` files are convenience kits for loading the
same sounds into Sitala.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import struct
import textwrap
import wave
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

DEFAULT_SOURCE = Path("/Library/Application Support/Electronik Sound Lab/Drumart SLD")
DEFAULT_SAMPLES_DIR = Path.home() / "Dropbox/Production/sample/Drumart SLD"
DEFAULT_KITS_DIR = Path.home() / "Library/Application Support/Sitala/User Kits"

_AUDIO_PATH_SUFFIXES = (b".flac\x00", b".wav\x00", b".aif\x00", b".aiff\x00")
_SAMPLE_METADATA = struct.Struct("<5I")


@dataclass(frozen=True)
class DrumartSample:
    """A decoded sample entry from a Drumart SLD bank."""

    slot: int
    source_path: str
    channels: int
    sample_rate: int
    frames: int
    pcm: bytes

    @property
    def filename(self) -> str:
        """Return a stable WAV filename for the sample."""
        return f"{self.slot + 1:02d} - Pad {self.slot + 1}.wav"

    @property
    def duration_ms(self) -> float:
        """Return the sample duration in milliseconds."""
        return self.frames / self.sample_rate * 1000


@dataclass(frozen=True)
class DrumartKit:
    """A Drumart SLD bank and its decoded sample entries."""

    label: str
    bank_file: Path
    samples: tuple[DrumartSample, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract Drumart SLD .mse banks into WAV files and Sitala kits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              Dry-run every Drumart SLD kit:
                uv run python -m scripts.migrate_drumart_sld

              Migrate one kit to the default global library locations:
                uv run python -m scripts.migrate_drumart_sld --only "[SLD] Hitmag" --write

              Migrate one kit into a REAPER project folder for portability:
                uv run python -m scripts.migrate_drumart_sld \\
                  --only "[SLD] Hitmag" \\
                  --samples-dir "$HOME/Documents/REAPER Media/Breathe/Media/Samples/Drumart SLD" \\
                  --kits-dir "$HOME/Documents/REAPER Media/Breathe/Media/Sitala Kits" \\
                  --write

            The standalone WAVs are useful in any sampler. The .sitala files are
            bundled Sitala kits for quick loading, but project archives should keep
            their own local WAV copies when portability matters.
            """
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Directory containing Drumart SLD .mse banks. Default: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=DEFAULT_SAMPLES_DIR,
        help=(
            f"Directory for standalone extracted WAVs. Default: {DEFAULT_SAMPLES_DIR}"
        ),
    )
    parser.add_argument(
        "--kits-dir",
        type=Path,
        default=DEFAULT_KITS_DIR,
        help=f"Directory for generated .sitala kits. Default: {DEFAULT_KITS_DIR}",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only migrate a kit with this label, such as '[SLD] Hitmag'.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write extracted WAVs and Sitala kits. Omit for a dry run.",
    )
    return parser.parse_args(argv)


def iter_kits(source: Path, only: Iterable[str] = ()) -> Iterable[DrumartKit]:
    """Yield decoded Drumart kits from a source directory."""
    requested = frozenset(only)
    for bank_file in sorted(source.glob("*.mse")):
        label = bank_file.stem
        if requested and label not in requested:
            continue

        kit = parse_kit(bank_file)
        if kit.samples or label in requested:
            yield kit


def parse_kit(bank_file: Path) -> DrumartKit:
    """Parse a Drumart SLD `.mse` file."""
    return parse_kit_bytes(
        bank_file.read_bytes(), label=bank_file.stem, bank_file=bank_file
    )


def parse_kit_bytes(data: bytes, *, label: str, bank_file: Path) -> DrumartKit:
    """Parse Drumart SLD bank bytes."""
    samples = tuple(
        sample
        for slot, record in enumerate(_iter_sample_records(data))
        if (sample := _sample_from_record(slot, data, record)) is not None
    )
    return DrumartKit(label=label, bank_file=bank_file, samples=samples)


def write_kit(kit: DrumartKit, *, samples_dir: Path, kits_dir: Path) -> None:
    """Write extracted WAVs and a bundled Sitala kit for a Drumart kit."""
    kit_samples_dir = samples_dir / kit.label
    kit_samples_dir.mkdir(parents=True, exist_ok=True)
    kits_dir.mkdir(parents=True, exist_ok=True)

    wavs = [(sample, wav_bytes(sample)) for sample in kit.samples]
    for sample, data in wavs:
        (kit_samples_dir / sample.filename).write_bytes(data)

    kit_path = kits_dir / f"{kit.label}.sitala"
    with zipfile.ZipFile(kit_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for sample, data in wavs:
            archive.writestr(f"Samples/{sample.filename}", data)
        archive.writestr("kit1.xml", sitala_xml(kit, wavs))


def wav_bytes(sample: DrumartSample) -> bytes:
    """Encode a decoded sample as a WAV file."""
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(sample.channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample.sample_rate)
        wav_file.writeframes(sample.pcm)
    return output.getvalue()


def sitala_xml(kit: DrumartKit, wavs: Sequence[tuple[DrumartSample, bytes]]) -> str:
    """Build the Sitala kit XML for decoded samples."""
    sounds = "\n".join(_sound_xml(sample, data) for sample, data in wavs)
    label = escape(kit.label)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sitala version="5" minorVersion="1" creator="music migrate_drumart_sld">
  <kit label="{label}">
    <sounds>
{sounds}
    </sounds>
    <meta creator="Electronik Sound Lab" description="Extracted from Drumart SLD"/>
  </kit>
</sitala>
"""


def main(argv: Sequence[str] | None = None) -> None:
    """Run the migration script."""
    args = parse_args(argv)
    kits = list(iter_kits(args.source, args.only))

    if args.only:
        found = {kit.label for kit in kits}
        missing = sorted(set(args.only) - found)
        if missing:
            names = ", ".join(missing)
            raise SystemExit(f"Could not find requested Drumart SLD kit(s): {names}")

    if not kits:
        raise SystemExit(f"No Drumart SLD kits found in {args.source}")

    for kit in kits:
        print(f"{kit.label}: {len(kit.samples)} samples")
        if args.write:
            write_kit(kit, samples_dir=args.samples_dir, kits_dir=args.kits_dir)
            print(f"  wrote WAVs to {args.samples_dir / kit.label}")
            print(f"  wrote Sitala kit to {args.kits_dir / f'{kit.label}.sitala'}")

    if not args.write:
        print("Dry run only. Re-run with --write to create files.")


def _iter_sample_records(data: bytes) -> Iterable[tuple[int, int, str]]:
    records: list[tuple[int, int, str]] = []
    for suffix in _AUDIO_PATH_SUFFIXES:
        position = 0
        while True:
            suffix_index = data.find(suffix, position)
            if suffix_index == -1:
                break

            path_start = data.rfind(b"\x00", 0, suffix_index) + 1
            raw_path = data[path_start : suffix_index + len(suffix) - 1]
            path = raw_path.decode("latin1", errors="replace")
            record_end = suffix_index + len(suffix)
            if "SAMPLES" in path.upper():
                records.append((path_start, record_end, path))

            position = suffix_index + 1

    yield from sorted(records)


def _sample_from_record(
    slot: int, data: bytes, record: tuple[int, int, str]
) -> DrumartSample | None:
    _, record_end, path = record
    metadata_end = record_end + _SAMPLE_METADATA.size
    if metadata_end > len(data):
        return None

    channels, sample_rate, sample_width, _, frames = _SAMPLE_METADATA.unpack_from(
        data, record_end
    )
    if channels == 0 or sample_rate == 0 or sample_width != 2 or frames == 0:
        return None

    sample_bytes = channels * sample_width * frames
    pcm_start = metadata_end
    pcm_end = pcm_start + sample_bytes
    if pcm_end > len(data):
        return None

    return DrumartSample(
        slot=slot,
        source_path=path,
        channels=channels,
        sample_rate=sample_rate,
        frames=frames,
        pcm=data[pcm_start:pcm_end],
    )


def _sound_xml(sample: DrumartSample, data: bytes) -> str:
    name = escape(f"Pad {sample.slot + 1}")
    filename = escape(f"Samples/{sample.filename}")
    digest = hashlib.md5(data).hexdigest()  # noqa: S324
    hold_ms = sample.duration_ms
    return f"""      <sound slot="{sample.slot}" name="{name}" md5="{digest}" sampleStart="0"
             sampleEnd="{sample.frames}" internal="{filename}">
        <chokeGroup>
          <item index="{sample.slot}"/>
        </chokeGroup>
        <parameters>
          <volume db="0.0"/>
          <shape macro="0.5">
            <attack ms="0.0"/>
            <hold ms="{hold_ms}"/>
            <decay ms="0.0"/>
            <makeup db="0.0"/>
          </shape>
          <compression macro="0.0">
            <bypassed/>
          </compression>
          <tuning ct="0.0"/>
          <pan position="C"/>
          <tone macro="0.5">
            <lowPass hz="22000.0" q="0.699999988079071"/>
            <notch hz="400.0" gainDb="0.0" q="3.5"/>
            <highPass hz="1.0" q="0.699999988079071"/>
          </tone>
        </parameters>
      </sound>"""


if __name__ == "__main__":  # pragma: no cover
    main()
