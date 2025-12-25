"""Utilities for working with Reaper projects."""

import json
import warnings
from pathlib import Path
from typing import Any, cast

import aiohttp

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Can't reach distant API")
    import reapy


# File: Render project, using the most recent render settings, auto-close render dialog
RENDER_CMD_ID = 42230


class ExtendedProject(reapy.core.Project):
    """Extend reapy.core.Project with additional properties."""

    def __init__(self) -> None:
        """Wrap common error in a more helpful message."""
        try:
            super().__init__()
        except AttributeError as aterr:
            if "module" in str(aterr) and "reascript_api" in str(aterr):
                raise Exception(
                    "Error while loading Reaper project. Is Reaper running?"
                ) from aterr
            raise  # pragma: no cover

    @classmethod
    def get_or_open(cls, project_dir: Path) -> "ExtendedProject":
        """Open the target Reaper project if it is not already open."""
        project = cls()
        if project_dir is None or str(project_dir.resolve()) == project.path:
            return project

        project_file = (
            project_dir
            if project_dir.suffix == ".rpp"
            else project_dir / f"{project_dir.name}.rpp"
        )
        reapy.RPR.Main_openProject(str(project_file))  # type: ignore[attr-defined]
        return cls()

    @property
    def metadata(self) -> dict[str, Any]:
        """Parse optional author-idiosyncratic metadata from the project notes."""
        notes = reapy.RPR.GetSetProjectNotes(-1, False, "", 999)[2]  # type: ignore[attr-defined]
        try:
            di = json.loads(notes)
        except json.JSONDecodeError:
            return {}

        return cast(dict[str, Any], di)

    async def render(self) -> None:
        """Trigger Reaper to render the currently open project.

        Unlike sending a command via Reaper's Python API
        (`project.perform_action(action_id)`), this method uses Reaper's HTTP
        API, to work async.
        """
        port = reapy.config.WEB_INTERFACE_PORT

        timeout_for_complex_project_stems = aiohttp.ClientTimeout(
            total=60 * 60 * 2  # 2 hours
        )

        async with aiohttp.ClientSession() as client:
            resp = await client.get(
                f"http://localhost:{port}/_/{RENDER_CMD_ID}",
                timeout=timeout_for_complex_project_stems,
            )
            resp.raise_for_status()

    @property
    def path(self) -> str:
        """Override. Get the path containing the project.

        Works around a bug in reapy 0.10.0's implementation of `Project.path`,
        which actually gets the _recording_ path of the project.
        """
        filename = str(reapy.RPR.EnumProjects(-1, None, 999)[2])  # type: ignore[attr-defined]
        return str(Path(filename).parent)
