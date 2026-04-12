"""Analyze command tests."""

import base64
import plistlib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.commands.analyze import process
from music.commands.analyze.command import main as analyze


@pytest.fixture(autouse=True)
def clear_jsfx_file_cache() -> Iterator[None]:
    """Isolate cached JSFX path lookups between tests."""
    process._jsfx_file.cache_clear()
    process._installed_au_names.cache_clear()
    process._installed_vst_names.cache_clear()
    yield
    process._jsfx_file.cache_clear()
    process._installed_au_names.cache_clear()
    process._installed_vst_names.cache_clear()


def test_main_plugins_for_project_file(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test plugin listing handles direct .rpp file inputs."""
    project_file = tmp_path / "Example.rpp"
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Lead Vox"
    <FXCHAIN
      <VST "VST3: Zebra2" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <VST "VST3: ValhallaRoom" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <VST "VST3: Zebra2" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        dmFsaWQ=
      >
      <JS "utility/KanakaMSEncoder1" "" 0 0<
        dmFsaWQ=
      >
      <JS "ReJJ/ReEQ/ReEQ.jsfx" "" 0 0<
        dmFsaWQ=
      >
      <CLAP "CLAPi: Surge XT" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <LV2 "LV2: Dragonfly Hall Reverb" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <DX "DX: Classic Compressor" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
  <TRACK
    NAME "Drum Bus"
    <FXCHAIN
      <VST "VST3: Zebra2" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    effects_dir = tmp_path / "Effects"
    components_dir = tmp_path / "Components"
    (effects_dir / "utility").mkdir(parents=True)
    (effects_dir / "ReJJ" / "ReEQ").mkdir(parents=True)
    components_dir.mkdir()
    (effects_dir / "utility" / "KanakaMSEncoder1").write_text("desc:Mid/Side Encoder\n")
    (effects_dir / "ReJJ" / "ReEQ" / "ReEQ.jsfx").write_text("desc:ReEQ\n")
    (components_dir / "Arcade.component").write_text("")

    with (
        mock.patch.object(process, "_jsfx_search_paths", return_value=(effects_dir,)),
        mock.patch.object(process, "_au_search_paths", return_value=(components_dir,)),
    ):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_formats_jsfx_names_with_prefix(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test JSFX entries use human-readable names from effect metadata."""
    project_file = tmp_path / "Example.rpp"
    effects_dir = tmp_path / "Effects"
    (effects_dir / "analysis").mkdir(parents=True)
    (effects_dir / "ReJJ" / "ReEQ").mkdir(parents=True)
    (effects_dir / "analysis" / "loudness_meter").write_text(
        "desc:Loudness Meter Peak/RMS/LUFS (Cockos)\n"
    )
    (effects_dir / "ReJJ" / "ReEQ" / "ReEQ.jsfx").write_text("desc:ReEQ\n")
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Analysis"
    <FXCHAIN
      <JS "analysis/loudness_meter" "" 0 0<
        dmFsaWQ=
      >
      <JS "ReJJ/ReEQ/ReEQ.jsfx" "" 0 0<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_jsfx_search_paths", return_value=(effects_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_reads_legacy_encoded_jsfx_metadata(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test JSFX metadata is read from non-UTF-8 effect files."""
    project_file = tmp_path / "Example.rpp"
    effects_dir = tmp_path / "Effects"
    (effects_dir / "loser").mkdir(parents=True)
    (effects_dir / "loser" / "masterLimiter").write_bytes(
        b"desc:Master Limiter\n// Andr\xe9\n"
    )
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Master"
    <FXCHAIN
      <JS "loser/masterLimiter" "" 0 0<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_jsfx_search_paths", return_value=(effects_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_falls_back_to_clean_jsfx_basename(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test JSFX entries fall back to a cleaned basename when metadata is missing."""
    project_file = tmp_path / "Example.rpp"
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    <FXCHAIN
      <JS "utility/KanakaMSEncoder1" "" 0 0<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_jsfx_search_paths", return_value=()):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_warns_for_missing_au_plugin(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test plugin mode warns when an AU saved in the project is not installed."""
    project_file = tmp_path / "Example.rpp"
    components_dir = tmp_path / "Components"
    components_dir.mkdir()
    (components_dir / "Captain Chords Epic Audio.component").write_text("")
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Synth - Chords"
    <FXCHAIN
      <AU "AUi: Captain Chords (Mixed In Key LLC)" "Mixed In Key: Captain Chords" "" 1234<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_au_search_paths", return_value=(components_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_warns_for_missing_jsfx_plugin(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test plugin mode warns when a JSFX path is not installed locally."""
    project_file = tmp_path / "Example.rpp"
    effects_dir = tmp_path / "Effects"
    effects_dir.mkdir()
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "EQ"
    <FXCHAIN
      <JS "ReJJ/ReEQ/ReEQ.jsfx" "" 0 0<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_jsfx_search_paths", return_value=(effects_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_warns_for_missing_vst_plugin(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test plugin mode warns when a VST saved in the project is not installed."""
    project_file = tmp_path / "Example.rpp"
    vst3_dir = tmp_path / "VST3"
    vst3_dir.mkdir()
    (vst3_dir / "Captain Chords Epic.vst3").write_text("")
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Synth - Chords"
    <FXCHAIN
      <VST "VSTi: Captain Chords (Mixed In Key LLC)" "Captain Chords.vst" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_vst_search_paths", return_value=(vst3_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_renders_warnings_in_table_cells(tmp_path: Path) -> None:
    """Test plugin mode keeps warnings in the table instead of separate prints."""
    project_file = tmp_path / "Example.rpp"
    arcade_state = _arcade_au_state_base64(
        b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
        b"<Looper_Preset>"
        b'<info name="Downstream" uuid="downstream-kit" product_uuid="honey-product" version="1.3.0"/>'
        b"</Looper_Preset>"
        b"</state_info>"
    )
    project_file.write_text(
        f"""\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Rhythm"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {arcade_state}
      >
      <VST "VST3: Zebra2" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", str(project_file)]
    )

    assert result.stderr == ""
    assert result.exception is None
    assert "Warning:" not in result.stdout
    assert "❌" in result.stdout
    assert "⛓️‍💥 Downstream" in result.stdout


@mock.patch("music.utils.project.ExtendedProject", autospec=True)
def test_main_plugins_no_args(
    mock_project: mock.Mock, snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test plugin listing defaults to the current project's directory."""
    project_name = "Song Title Here"
    project_dir = tmp_path / "path" / "to" / project_name
    project_dir.mkdir(parents=True)
    (project_dir / f"{project_name}.rpp").write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    <FXCHAIN
      <VST "VSTi: Kontakt" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
>
"""
    )
    mock_project.return_value.path = project_dir

    result = CliRunner(catch_exceptions=False).invoke(analyze, ["--plugins"])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_raw_mode_sections(snapshot: SnapshotAssertion, tmp_path: Path) -> None:
    """Test raw mode prints decoded settings within project sections."""
    project_file = tmp_path / "Example.rpp"
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    <FXCHAIN
      <VST "VST3: Zebra2" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <AU "AU: Crystalline (BABY Audio)" "BABY Audio: Crystalline" "" 1234<
        bW9yZQ==
      >
      <JS "JS: Mid/Side Encoder" "" 0 0<
        anNm
      >
      <CLAP "CLAPi: Surge XT" "plugin" 0 "" 1234<
        Y2xhcA==
      >
      <LV2 "LV2: Dragonfly Hall Reverb" "plugin" 0 "" 1234<
        bHYy
      >
      <DX "DX: Classic Compressor" "plugin" 0 "" 1234<
        ZHg=
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_raw_mode_reassembles_chunked_arcade_state(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test raw mode prints one decoded Arcade state instead of chunk fragments."""
    project_file = tmp_path / "Example.rpp"
    long_name = "Downstream " + ("very-long-state " * 20)
    looper_info = (
        f'<info name="{long_name}" uuid="downstream-kit" '
        'product_uuid="honey-product" version="1.3.0"/>'
    ).encode()
    arcade_state = _arcade_au_state_base64(
        b'<?xml version="1.0" encoding="UTF-8"?><state_info><Looper_Preset>'
        + looper_info
        + b"</Looper_Preset></state_info>"
    )
    chunked_state = "\n".join(
        f"        {arcade_state[i : i + 128]}" for i in range(0, len(arcade_state), 128)
    )
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
{chunked_state}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_warns_for_arcade_hyperion_missing_source(
    snapshot: SnapshotAssertion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Arcade Hyperion presets warn when their source content is missing."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids=set(), source_uuids=set())

    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Bass note kit"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {
            _arcade_au_state_base64(
                b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
                b"<Hyperion_Preset>"
                b'<info name="Amped Up" uuid="kit-uuid" product_uuid="product-uuid" version="2.0.0"/>'
                b"<model>"
                b'<HyperionLoadedSource LoadedSourceUuid="missing-source"/>'
                b'<HyperionFxBusSettings Name="error"/>'
                b"</model>"
                b"</Hyperion_Preset>"
                b"</state_info>"
            )
        }
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])
    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_does_not_warn_for_arcade_hyperion_installed_source(
    snapshot: SnapshotAssertion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Arcade Hyperion presets stay quiet once source content is installed."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids=set(), source_uuids={"loaded-source"})

    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Bass note kit"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {
            _arcade_au_state_base64(
                b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
                b"<Hyperion_Preset>"
                b'<info name="Amped Up" uuid="kit-uuid" product_uuid="product-uuid" version="2.0.0"/>'
                b"<model>"
                b'<HyperionLoadedSource LoadedSourceUuid="loaded-source"/>'
                b'<HyperionFxBusSettings Name="error"/>'
                b"</model>"
                b"</Hyperion_Preset>"
                b"</state_info>"
            )
        }
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_resolves_arcade_hyperion_source_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test plugin mode prefers human-readable Arcade source names in warnings."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(
        db_path,
        kit_uuids=set(),
        source_uuids={"installed-source"},
        source_names={"installed-source": "Installed"},
    )

    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Bass note kit"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {
            _arcade_au_state_base64(
                b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
                b"<Hyperion_Preset>"
                b'<info name="Amped Up" uuid="kit-uuid" product_uuid="product-uuid" version="2.0.0"/>'
                b"<model>"
                b'<HyperionLoadedSource LoadedSourceUuid="missing-source" LoadedSourceName="Amped Up Main"/>'
                b'<HyperionLoadedSource LoadedSourceUuid="installed-source"/>'
                b"</model>"
                b"</Hyperion_Preset>"
                b"</state_info>"
            )
        }
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", str(project_file)]
    )

    assert result.stderr == ""
    assert result.exception is None
    assert "⛓️‍💥 Amped Up Main" in result.stdout
    assert "missing-source" not in result.stdout


def test_main_plugins_falls_back_to_arcade_hyperion_preset_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test plugin mode uses the Hyperion preset name if source names are unavailable."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids=set(), source_uuids=set())

    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Bass note kit"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {
            _arcade_au_state_base64(
                b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
                b"<Hyperion_Preset>"
                b'<info name="Amped Up" uuid="kit-uuid" product_uuid="product-uuid" version="2.0.0"/>'
                b"<model>"
                b'<HyperionLoadedSource LoadedSourceUuid="missing-source"/>'
                b"</model>"
                b"</Hyperion_Preset>"
                b"</state_info>"
            )
        }
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", str(project_file)]
    )

    assert result.stderr == ""
    assert result.exception is None
    assert "⛓️‍💥 Amped Up" in result.stdout
    assert "missing-source" not in result.stdout


def test_main_warns_for_arcade_looper_missing_kit(
    snapshot: SnapshotAssertion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Arcade looper presets warn when the kit is not installed locally."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids={"some-other-kit"}, source_uuids=set())

    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Rhythm"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {
            _arcade_au_state_base64(
                b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
                b"<Looper_Preset>"
                b'<info name="Downstream" uuid="downstream-kit" product_uuid="honey-product" version="1.3.0"/>'
                b"</Looper_Preset>"
                b"</state_info>"
            )
        }
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_does_not_warn_for_arcade_looper_installed_kit(
    snapshot: SnapshotAssertion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Arcade looper presets stay quiet once the kit exists in local DB."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids={"downstream-kit"}, source_uuids=set())

    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Rhythm"
    <FXCHAIN
      <AU "AUi: Arcade (Output)" "Output: Arcade" "" 1234<
        {
            _arcade_au_state_base64(
                b'<?xml version="1.0" encoding="UTF-8"?><state_info>'
                b"<Looper_Preset>"
                b'<info name="Downstream" uuid="downstream-kit" product_uuid="honey-product" version="1.3.0"/>'
                b"</Looper_Preset>"
                b"</state_info>"
            )
        }
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def _arcade_au_state_base64(juce_state: bytes) -> str:
    """Build a minimal Arcade AU state chunk for tests."""
    outer = plistlib.dumps(
        {
            "data": b"",
            "jucePluginState": b"prefix-bytes" + juce_state + b"trailing-bytes",
            "name": "Untitled",
        }
    )
    return base64.b64encode(outer).decode("ascii")


def _write_arcade_db(
    db_path: Path,
    kit_uuids: set[str],
    source_uuids: set[str],
    source_names: dict[str, str] | None = None,
) -> None:
    """Create a minimal Arcade metadata DB for tests."""
    import sqlite3

    source_names = source_names or {}
    with closing(sqlite3.connect(db_path)) as con:
        con.execute("create table kits (uuid text)")
        con.execute("create table sound_sources (uuid text, name text)")
        con.executemany(
            "insert into kits (uuid) values (?)", [(uuid,) for uuid in kit_uuids]
        )
        con.executemany(
            "insert into sound_sources (uuid, name) values (?, ?)",
            [
                (uuid, source_names.get(uuid))
                for uuid in source_uuids | source_names.keys()
            ],
        )
        con.commit()
