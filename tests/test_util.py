"""Util tests."""

from pathlib import Path
from unittest import mock

import music.util
import pytest
from syrupy.assertion import SnapshotAssertion


@mock.patch("reapy.core.Project.__init__")
def test_project_reaper_not_running(core_project: mock.Mock) -> None:
    """Test handling when Reaper is not running."""
    with pytest.raises(Exception, match="Reaper running"):
        core_project.side_effect = AttributeError(
            "module doesn't have reascript_api, yo"
        )
        music.util.ExtendedProject()


@mock.patch("reapy.core.Project.__init__")
@mock.patch("reapy.RPR.EnumProjects", create=True)
def test_project_path(
    enum_projects: mock.Mock,
    core_project: mock.Mock,
    tmp_path: Path,
) -> None:
    """Test getting the path containing the project (not the _recording_ path)."""
    some_path = tmp_path / "path" / "to" / "some project"
    some_file = some_path / "some project.rpp"
    enum_projects.return_value = ("", "", some_path / some_file)
    obj = music.util.ExtendedProject()
    assert obj.path == str(some_path)


@mock.patch("reapy.core.Project.__init__")
@mock.patch("reapy.RPR.EnumProjects", create=True)
@mock.patch("reapy.RPR.Main_openProject", create=True)
def test_project_open(
    open_project: mock.Mock,
    enum_projects: mock.Mock,
    core_project: mock.Mock,
    snapshot: SnapshotAssertion,
    tmp_path: Path,
) -> None:
    """Test invoking Reaper to open a project."""
    some_path = tmp_path / "path" / "to" / "some project"
    music.util.ExtendedProject(some_path)
    assert open_project.mock_calls == snapshot
