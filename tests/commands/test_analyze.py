"""Analyze command tests."""

import base64
import plistlib
import re
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from music.commands.analyze import process
from music.commands.analyze.command import main as analyze
from music.commands.analyze.vendors.spitfire import labs


def _plugin_sort_fixture_project(project_file: Path) -> None:
    """Write a project fixture whose plugin order changes across sort modes."""
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Zulu"
    <FXCHAIN
      <VST "VST3: Bravo" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
      <VST "VST3: Alpha" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
  <TRACK
    NAME "Alpha"
    <FXCHAIN
      <VST "VST3: Charlie" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
  <TRACK
    NAME "Bravo"
    <FXCHAIN
      <VST "VST3: Alpha" "plugin" 0 "" 1234<
        dmFsaWQ=
      >
    >
  >
>
"""
    )


def _plugin_row_values(stdout: str) -> list[tuple[str, int, str]]:
    """Return plugin row values from the rendered table."""
    rows = []
    for line in stdout.splitlines():
        if "VST3:" not in line:
            continue

        cells = [cell.strip() for cell in re.split(r"[│┃]", line) if cell.strip()]
        rows.append((cells[0], int(cells[1]), cells[2]))

    return rows


@pytest.fixture(autouse=True)
def clear_jsfx_file_cache() -> Iterator[None]:
    """Isolate cached JSFX path lookups between tests."""
    process._jsfx_file.cache_clear()
    process._installed_au_names.cache_clear()
    process._installed_au_plugins.cache_clear()
    process._installed_vst_names.cache_clear()
    process._installed_vst_plugins_by_name.cache_clear()
    process._binary_architectures.cache_clear()
    labs._installed_labs_families.cache_clear()
    yield
    process._jsfx_file.cache_clear()
    process._installed_au_names.cache_clear()
    process._installed_au_plugins.cache_clear()
    process._installed_vst_names.cache_clear()
    process._installed_vst_plugins_by_name.cache_clear()
    process._binary_architectures.cache_clear()
    labs._installed_labs_families.cache_clear()


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
      BYPASS 1 0 0
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
    NAME "Muted Folder"
    MUTESOLO 1 0 0
    <TRACK
      NAME "Drum Bus"
      <FXCHAIN
        <VST "VST3: Zebra2" "plugin" 0 "" 1234<
          dmFsaWQ=
        >
      >
    >
  >
>
"""
    )

    effects_dir = tmp_path / "Effects"
    components_dir = tmp_path / "Components"
    vst3_dir = tmp_path / "VST3"
    (effects_dir / "utility").mkdir(parents=True)
    (effects_dir / "ReJJ" / "ReEQ").mkdir(parents=True)
    components_dir.mkdir()
    (vst3_dir / "Drumart SLD.vst3" / "Contents" / "MacOS").mkdir(parents=True)
    (effects_dir / "utility" / "KanakaMSEncoder1").write_text("desc:Mid/Side Encoder\n")
    (effects_dir / "ReJJ" / "ReEQ" / "ReEQ.jsfx").write_text("desc:ReEQ\n")
    (components_dir / "Arcade.component").write_text("")
    (vst3_dir / "Drumart SLD.vst3" / "Contents" / "MacOS" / "MSP").write_text("")
    project_file.write_text(
        project_file.read_text().replace(
            '      <DX "DX: Classic Compressor" "plugin" 0 "" 1234<\n'
            "        dmFsaWQ=\n"
            "      >\n",
            '      <DX "DX: Classic Compressor" "plugin" 0 "" 1234<\n'
            "        dmFsaWQ=\n"
            "      >\n"
            '      <VST "VST3i: Drumart SLD (ESL) (32 out)" "Drumart SLD.vst3" 0 "" 1234<\n'
            "        dmFsaWQ=\n"
            "      >\n",
        )
    )

    with (
        mock.patch.object(process, "_jsfx_search_paths", return_value=(effects_dir,)),
        mock.patch.object(process, "_au_search_paths", return_value=(components_dir,)),
        mock.patch.object(process, "_vst_search_paths", return_value=(vst3_dir,)),
        mock.patch.object(
            process,
            "_binary_architectures",
            return_value=frozenset({"x86_64"}),
        ),
    ):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_keeps_default_sort_order(tmp_path: Path) -> None:
    """Test plugin mode defaults to plugin, then track, then track name."""
    project_file = tmp_path / "Example.rpp"
    _plugin_sort_fixture_project(project_file)

    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", str(project_file)]
    )

    assert result.stderr == ""
    assert result.exception is None
    assert _plugin_row_values(result.stdout) == [
        ("VST3: Alpha", 1, "Zulu"),
        ("VST3: Alpha", 3, "Bravo"),
        ("VST3: Bravo", 1, "Zulu"),
        ("VST3: Charlie", 2, "Alpha"),
    ]


def test_main_plugins_sort_plugin_matches_default_order(tmp_path: Path) -> None:
    """Test explicit plugin sorting matches the default plugin-mode order."""
    project_file = tmp_path / "Example.rpp"
    _plugin_sort_fixture_project(project_file)

    default_result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", str(project_file)]
    )
    sorted_result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", "--sort", "plugin", str(project_file)]
    )

    assert default_result.stderr == ""
    assert default_result.exception is None
    assert sorted_result.stderr == ""
    assert sorted_result.exception is None
    assert _plugin_row_values(sorted_result.stdout) == (
        _plugin_row_values(default_result.stdout)
    )


def test_main_plugins_sort_track_orders_by_track_number(tmp_path: Path) -> None:
    """Test plugin mode can sort rows by track number first."""
    project_file = tmp_path / "Example.rpp"
    _plugin_sort_fixture_project(project_file)

    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", "--sort", "track", str(project_file)]
    )

    assert result.stderr == ""
    assert result.exception is None
    assert _plugin_row_values(result.stdout) == [
        ("VST3: Alpha", 1, "Zulu"),
        ("VST3: Bravo", 1, "Zulu"),
        ("VST3: Charlie", 2, "Alpha"),
        ("VST3: Alpha", 3, "Bravo"),
    ]


def test_main_plugins_sort_track_name_orders_by_track_name(tmp_path: Path) -> None:
    """Test plugin mode can sort rows by track name first."""
    project_file = tmp_path / "Example.rpp"
    _plugin_sort_fixture_project(project_file)

    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", "--sort", "track-name", str(project_file)]
    )

    assert result.stderr == ""
    assert result.exception is None
    assert _plugin_row_values(result.stdout) == [
        ("VST3: Charlie", 2, "Alpha"),
        ("VST3: Alpha", 3, "Bravo"),
        ("VST3: Alpha", 1, "Zulu"),
        ("VST3: Bravo", 1, "Zulu"),
    ]


def test_main_sort_requires_plugins() -> None:
    """Test --sort is rejected outside plugin table mode."""
    result = CliRunner(catch_exceptions=False).invoke(analyze, ["--sort", "track"])

    assert result.exit_code == 2
    assert result.exception is not None
    assert "--sort is only supported together with --plugins" in result.stderr
    assert "--sort is only supported together with --plugins" in result.output


def test_main_sort_rejects_unknown_value() -> None:
    """Test Click rejects unsupported plugin sort keys."""
    result = CliRunner(catch_exceptions=False).invoke(
        analyze, ["--plugins", "--sort", "warning"]
    )

    assert result.exit_code == 2
    assert result.exception is not None
    assert "Invalid value for '--sort'" in result.stderr
    assert "Invalid value for '--sort'" in result.output


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

    with (
        mock.patch.object(process, "_audio_units_supported", return_value=True),
        mock.patch.object(process, "_au_search_paths", return_value=(components_dir,)),
    ):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_plugins_skips_au_install_check_when_audio_units_unsupported(
    tmp_path: Path,
) -> None:
    """Test AU install warnings stay silent on platforms without Audio Units."""
    project_file = tmp_path / "Example.rpp"
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

    with mock.patch.object(process, "_audio_units_supported", return_value=False):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert result.stderr == ""
    assert result.exception is None
    assert "does not appear to be installed locally" not in result.stdout


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


def test_main_plugins_detects_nested_vst3_shell_plugins(tmp_path: Path) -> None:
    """Test VST shell plugins are detected from nested bundle layouts."""
    project_file = tmp_path / "Example.rpp"
    vst3_dir = tmp_path / "VST3"
    shell_dir = vst3_dir / "MeldaProduction" / "Modulation" / "MAutopan.vst3"
    shell_dir.mkdir(parents=True)
    project_file.write_text(
        """\
<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Vfx"
    <FXCHAIN
      <VST "VST3: MAutopan (MeldaProduction)" "MAutopan.vst3" 0 "" 1234<
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

    assert result.stderr == ""
    assert result.exception is None
    assert "❌ Not installed" not in result.stdout


def test_main_plugins_renders_warnings_in_table_cells(
    snapshot: SnapshotAssertion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test plugin mode keeps warnings in the table instead of separate prints."""
    project_file = tmp_path / "Example.rpp"
    components_dir = tmp_path / "Components"
    db_path = tmp_path / "arcade.db"
    (components_dir / "Arcade.component" / "Contents" / "MacOS").mkdir(parents=True)
    (components_dir / "Arcade.component" / "Contents" / "MacOS" / "Arcade").write_text(
        ""
    )
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids=set(), source_uuids=set())
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

    with (
        mock.patch.object(process, "_audio_units_supported", return_value=True),
        mock.patch.object(process, "_au_search_paths", return_value=(components_dir,)),
        mock.patch.object(
            process,
            "_binary_architectures",
            return_value=frozenset({"x86_64"}),
        ),
    ):
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


def test_main_raw_mode_sections(snapshot: SnapshotAssertion, tmp_path: Path) -> None:
    """Test raw mode prints decoded settings within project sections."""
    project_dir = tmp_path / "Example"
    project_dir.mkdir()
    project_file = project_dir / "Example.rpp"
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    <FXCHAIN
      <VST "VST3: Instrument Metadata" "plugin" 0 "" 1234<
        abcde
      >
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

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_dir)])

    assert (result.stderr, result.exception, result.stdout) == snapshot


def test_main_warns_for_missing_project_media_file(tmp_path: Path) -> None:
    """Test saved media references warn when the target file is missing."""
    project_file = tmp_path / "Example.rpp"
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Audio"
    <ITEM
      <SOURCE WAVE
        FILE "Media/kick.wav"
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    output = result.stdout.replace("\n", "")
    assert 'Project media file "Media/kick.wav" does not exist' in output
    assert str(tmp_path / "Media" / "kick.wav") in output


def test_main_warns_for_external_project_media_file(tmp_path: Path) -> None:
    """Test saved media references warn when they live outside the project folder."""
    project_file = tmp_path / "Project" / "Example.rpp"
    project_file.parent.mkdir()
    external_file = tmp_path / "Samples" / "kick.wav"
    external_file.parent.mkdir()
    external_file.write_text("audio")
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Audio"
    <ITEM
      <SOURCE WAVE
        FILE "../Samples/kick.wav"
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    output = result.stdout.replace("\n", "")
    assert 'Project media file "../Samples/kick.wav" is outside' in output
    assert str(external_file) in output


def test_main_does_not_warn_for_existing_project_media_file(tmp_path: Path) -> None:
    """Test project-local media references stay quiet when the target file exists."""
    project_file = tmp_path / "Example.rpp"
    media_file = tmp_path / "Media" / "kick.wav"
    media_file.parent.mkdir()
    media_file.write_text("audio")
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Audio"
    <ITEM
      <SOURCE WAVE
        FILE "Media/kick.wav"
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    assert "Project media file" not in result.stdout


def test_main_warns_for_reasamplomatic5000_missing_sample(tmp_path: Path) -> None:
    """Test ReaSamplOmatic5000 sample paths warn when the target is missing."""
    project_file = tmp_path / "Example.rpp"
    sample_file = tmp_path / "Media" / "Kick.wav"
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Drums"
    <FXCHAIN
      <VST "VSTi: ReaSamplOmatic5000 (Cockos)" "reasamplomatic.vst.dylib" 0 "" 1234<
        {_plugin_state_base64(f"prefix {sample_file}".encode())}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    output = result.stdout.replace("\n", "")
    assert (
        'Plugin "VSTi: ReaSamplOmatic5000 (Cockos)" on track 1 "Drums" '
        f"references missing sample: {sample_file}"
    ) in output


def test_main_plugins_warns_for_reasamplomatic5000_external_sample(
    tmp_path: Path,
) -> None:
    """Test ReaSamplOmatic5000 external samples appear in plugin warning cells."""
    project_dir = tmp_path / "Project"
    project_dir.mkdir()
    project_file = project_dir / "Example.rpp"
    sample_file = tmp_path / "Samples" / "Kick.wav"
    sample_file.parent.mkdir()
    sample_file.write_text("audio")
    vst_dir = tmp_path / "VST"
    vst_dir.mkdir()
    (vst_dir / "reasamplomatic.vst.dylib").write_text("")
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Drums"
    <FXCHAIN
      <VST "VSTi: ReaSamplOmatic5000 (Cockos)" "reasamplomatic.vst.dylib" 0 "" 1234<
        {_plugin_state_base64(f"prefix {sample_file}".encode())}
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_vst_search_paths", return_value=(vst_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert result.stderr == ""
    assert result.exception is None
    assert "⛓️‍💥 Kick.wav" in result.stdout


def test_main_does_not_warn_for_reasamplomatic5000_project_sample(
    tmp_path: Path,
) -> None:
    """Test ReaSamplOmatic5000 stays quiet for existing project-local samples."""
    project_file = tmp_path / "Example.rpp"
    sample_file = tmp_path / "Media" / "Kick.wav"
    sample_file.parent.mkdir()
    sample_file.write_text("audio")
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Drums"
    <FXCHAIN
      <VST "VSTi: ReaSamplOmatic5000 (Cockos)" "reasamplomatic.vst.dylib" 0 "" 1234<
        {_plugin_state_base64(f"prefix {sample_file}".encode())}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    assert "ReaSamplOmatic5000" not in result.stdout


def test_main_warns_for_sitala_home_url_missing_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test Sitala's home-relative file URLs are resolved before checking files."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    project_file = tmp_path / "Example.rpp"
    sitala_state = _sitala_state(
        "file://:home:/Samples/Kick%20One.wav",
        sound_name="Kick One",
    )
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Sitala"
    <FXCHAIN
      <VST "VST3i: Sitala (Decomposer) (32 out)" "Sitala.vst3" 0 "" 1234<
        {_plugin_state_base64(sitala_state)}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    output = result.stdout.replace("\n", "")
    assert (
        'Plugin "VST3i: Sitala (Decomposer) (32 out)" on track 1 "Sitala" '
        "references missing sample: file://:home:/Samples/Kick%20One.wav"
    ) in output


def test_main_plugins_warns_for_sitala_missing_sample_once(tmp_path: Path) -> None:
    """Test duplicate Sitala locations produce one compact warning."""
    project_file = tmp_path / "Example.rpp"
    missing_sample = tmp_path / "Media" / "Kick.wav"
    vst_dir = tmp_path / "VST3"
    vst_dir.mkdir()
    (vst_dir / "Sitala.vst3").write_text("")
    sitala_state = _sitala_state(str(missing_sample), str(missing_sample))
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Sitala"
    <FXCHAIN
      <VST "VST3i: Sitala (Decomposer) (32 out)" "Sitala.vst3" 0 "" 1234<
        {_plugin_state_base64(sitala_state)}
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_vst_search_paths", return_value=(vst_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert result.stderr == ""
    assert result.exception is None
    assert result.stdout.count("⛓️‍💥 Kick.wav") == 1


def test_main_does_not_warn_for_sitala_project_sample(tmp_path: Path) -> None:
    """Test Sitala stays quiet for existing project-local samples."""
    project_file = tmp_path / "Example.rpp"
    sample_file = tmp_path / "Media" / "Kick.wav"
    sample_file.parent.mkdir()
    sample_file.write_text("audio")
    sitala_state = _sitala_state(str(sample_file))
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Sitala"
    <FXCHAIN
      <VST "VST3i: Sitala (Decomposer) (32 out)" "Sitala.vst3" 0 "" 1234<
        {_plugin_state_base64(sitala_state)}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    assert "Sitala" not in result.stdout


def test_main_warns_for_labs_missing_au_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test AU LABS state warns when the saved family is not installed."""
    project_file = tmp_path / "Example.rpp"
    properties = tmp_path / "Spitfire.properties"
    properties.write_text('{"Labs": {"samples": []}}')
    monkeypatch.setenv("SPITFIRE_PROPERTIES_PATH", str(properties))
    labs._installed_labs_families.cache_clear()
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Choir"
    <FXCHAIN
      <AU "AUi: LABS (Spitfire Audio)" "Spitfire Audio: LABS" "" 1234<
        {_labs_au_state_base64(family="Gaelic Voices", preset_name="Oh Riser")}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    output = result.stdout.replace("\n", "")
    assert (
        'Plugin "AUi: LABS (Spitfire Audio)" on track 1 "Choir" '
        'references missing LABS library "Gaelic Voices" preset "Oh Riser"'
    ) in output
    labs._installed_labs_families.cache_clear()


def test_main_plugins_warns_for_labs_missing_vst_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test VST LABS state appears in plugin warning cells."""
    project_file = tmp_path / "Example.rpp"
    properties = tmp_path / "Spitfire.properties"
    properties.write_text('{"Labs": {"patches": []}}')
    monkeypatch.setenv("SPITFIRE_PROPERTIES_PATH", str(properties))
    labs._installed_labs_families.cache_clear()
    vst_dir = tmp_path / "VST3"
    vst_dir.mkdir()
    (vst_dir / "LABS.vst3").write_text("")
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Cello"
    <FXCHAIN
      <VST "VST3i: LABS (Spitfire Audio)" "LABS.vst3" 0 "" 1234<
        {_plugin_state_base64(_labs_xml(family="Cello Moods", preset_name="Gm Melancholy"))}
      >
    >
  >
>
"""
    )

    with mock.patch.object(process, "_vst_search_paths", return_value=(vst_dir,)):
        result = CliRunner(catch_exceptions=False).invoke(
            analyze, ["--plugins", str(project_file)]
        )

    assert result.stderr == ""
    assert result.exception is None
    assert "⛓️‍💥 Gm Melancholy" in result.stdout
    labs._installed_labs_families.cache_clear()


def test_main_does_not_warn_for_labs_installed_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test LABS stays quiet when Spitfire metadata includes the saved family."""
    project_file = tmp_path / "Example.rpp"
    properties = tmp_path / "Spitfire.properties"
    properties.write_text(
        '{"Labs": {"samples": ["/Library/Spitfire/LABS Cello Moods/Samples"]}}'
    )
    monkeypatch.setenv("SPITFIRE_PROPERTIES_PATH", str(properties))
    labs._installed_labs_families.cache_clear()
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Cello"
    <FXCHAIN
      <VST "VST3i: LABS (Spitfire Audio)" "LABS.vst3" 0 "" 1234<
        {_plugin_state_base64(_labs_xml(family="Cello Moods", preset_name="Gm Melancholy"))}
      >
    >
  >
>
"""
    )

    result = CliRunner(catch_exceptions=False).invoke(analyze, [str(project_file)])

    assert result.stderr == ""
    assert result.exception is None
    assert "references missing LABS library" not in result.stdout
    labs._installed_labs_families.cache_clear()


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
    snapshot: SnapshotAssertion, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    assert (result.stderr, result.exception, result.stdout) == snapshot


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


def test_main_plugins_warns_for_chunked_vst_arcade_looper_missing_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test plugin mode reads chunked VST Arcade state and surfaces missing kits."""
    project_file = tmp_path / "Example.rpp"
    db_path = tmp_path / "arcade.db"
    monkeypatch.setenv("ARCADE_DB_PATH", str(db_path))
    _write_arcade_db(db_path, kit_uuids=set(), source_uuids=set())
    arcade_state = "\n".join(
        base64.b64encode(chunk).decode("ascii")
        for chunk in (
            b"\x00" * 16,
            b'<?xml version="1.0" encoding="UTF-8"?><state_info>',
            b"<Looper_Preset>",
            b'<info name="Downstream" uuid="downstream-kit" product_uuid="honey-product" version="1.3.0"/>',
            b"</Looper_Preset></state_info>",
        )
    )
    project_file.write_text(
        f"""<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
    NAME "Rhythm"
    <FXCHAIN
      <VST "VST3i: Arcade (Output)" "Arcade.vst3" 0 "" 1234<
        {arcade_state.replace(chr(10), chr(10) + "        ")}
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
    assert "⛓️‍💥 Downstream" in result.stdout


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


def _plugin_state_base64(state: bytes) -> str:
    """Build a base64 plugin state chunk for tests."""
    return base64.b64encode(state).decode("ascii")


def _sitala_state(*locations: str, sound_name: str = "Kick") -> bytes:
    """Build minimal Sitala XML state for tests."""
    sounds = "\n".join(
        f'<sound slot="{slot}" location="{location}" name="{sound_name}"/>'
        for slot, location in enumerate(locations)
    )
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        + f"<sitala><state><sounds>{sounds}</sounds></state></sitala>".encode()
    )


def _labs_xml(*, family: str, preset_name: str) -> bytes:
    """Build minimal LABS XML state for tests."""
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        + f'<Labs><META family="{family}" name="{preset_name}"/></Labs>'.encode()
    )


def _labs_au_state_base64(*, family: str, preset_name: str) -> str:
    """Build a minimal LABS AU state chunk for tests."""
    outer = plistlib.dumps(
        {"jucePluginState": _labs_xml(family=family, preset_name=preset_name)}
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
