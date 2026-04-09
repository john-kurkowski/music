"""Analyze command tests."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from music.commands.analyze.command import main as analyze


def test_main_plugins_for_project_file(tmp_path: Path) -> None:
    """Test plugin listing handles direct .rpp file inputs."""
    project_file = tmp_path / "Example.rpp"
    project_file.write_text(
        """<REAPER_PROJECT 0.1 "6.0/x64" 0
  <TRACK
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
    assert result.stdout == (
        "─────────────────────────────────── Example ────────────────────────────────────\n"
        "  VST3: Zebra2\n"
        "  VST3: ValhallaRoom\n"
        "  VST3: Zebra2\n"
        "  AUi: Arcade (Output)\n"
    )


@mock.patch("music.utils.project.ExtendedProject", autospec=True)
def test_main_plugins_no_args(mock_project: mock.Mock, tmp_path: Path) -> None:
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

    assert result.stderr == ""
    assert result.exception is None
    assert "Song Title Here" in result.stdout
    assert result.stdout.endswith("  VSTi: Kontakt\n")


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
        "  valid\n"
        "  more\n"
    )
