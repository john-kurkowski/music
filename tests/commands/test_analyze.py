"""Analyze command tests."""

import base64
import plistlib
from contextlib import closing
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.commands.analyze import command
from music.commands.analyze.command import main as analyze


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
    (effects_dir / "utility").mkdir(parents=True)
    (effects_dir / "ReJJ" / "ReEQ").mkdir(parents=True)
    (effects_dir / "utility" / "KanakaMSEncoder1").write_text("desc:Mid/Side Encoder\n")
    (effects_dir / "ReJJ" / "ReEQ" / "ReEQ.jsfx").write_text("desc:ReEQ\n")
    command._jsfx_file.cache_clear()

    with mock.patch.object(command, "_jsfx_search_paths", return_value=(effects_dir,)):
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
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
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
    command._jsfx_file.cache_clear()

    with mock.patch.object(command, "_jsfx_search_paths", return_value=(effects_dir,)):
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
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
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
    command._jsfx_file.cache_clear()

    with mock.patch.object(command, "_jsfx_search_paths", return_value=(effects_dir,)):
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
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
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
    command._jsfx_file.cache_clear()

    with mock.patch.object(command, "_jsfx_search_paths", return_value=()):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


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


def test_main_raw_mode_sections(tmp_path: Path) -> None:
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

    assert result.stderr == ""
    assert result.exception is None
    assert result.stdout == (
        "─────────────────────────────────── Example ────────────────────────────────────\n"
        "  more\n"
        "  clap\n"
        "  dx\n"
        "  jsf\n"
        "  lv2\n"
        "  valid\n"
    )


def test_main_raw_mode_reassembles_chunked_arcade_state(tmp_path: Path) -> None:
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

    assert result.stderr == ""
    assert result.exception is None
    assert result.stdout.count("  <?xml version=") == 1
    assert 'name="Downstream' in result.stdout
    assert "prefix-bytes" not in result.stdout
    assert "more chars" in result.stdout


def test_main_warns_for_arcade_hyperion_missing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    assert result.stderr == ""
    assert result.exception is None
    assert 'Arcade instrument "Amped Up" on track "Bass note kit"' in result.stdout
    assert "references" in result.stdout
    assert "missing source content" in result.stdout
    assert "missing-source" in result.stdout
    assert "has an internal" in result.stdout
    assert '"error" state' in result.stdout


def test_main_does_not_warn_for_arcade_hyperion_installed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    assert result.stderr == ""
    assert result.exception is None
    assert "Arcade instrument" not in result.stdout


def test_main_warns_for_arcade_looper_missing_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    assert result.stderr == ""
    assert result.exception is None
    assert 'Arcade sampler "Downstream" on track "Rhythm"' in result.stdout
    assert "is not installed" in result.stdout
    assert "locally" in result.stdout
    assert "downstream-kit" in result.stdout


def test_main_does_not_warn_for_arcade_looper_installed_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    assert result.stderr == ""
    assert result.exception is None
    assert "Arcade sampler" not in result.stdout


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
    db_path: Path, kit_uuids: set[str], source_uuids: set[str]
) -> None:
    """Create a minimal Arcade metadata DB for tests."""
    import sqlite3

    with closing(sqlite3.connect(db_path)) as con:
        con.execute("create table kits (uuid text)")
        con.execute("create table sound_sources (uuid text)")
        con.executemany(
            "insert into kits (uuid) values (?)", [(uuid,) for uuid in kit_uuids]
        )
        con.executemany(
            "insert into sound_sources (uuid) values (?)",
            [(uuid,) for uuid in source_uuids],
        )
        con.commit()
