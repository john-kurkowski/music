"""Analyze command tests."""

from pathlib import Path
from unittest import mock

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
