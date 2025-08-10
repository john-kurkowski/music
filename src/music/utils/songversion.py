"""Enum of different versions of a song to render."""

import enum
from pathlib import Path

from . import assert_exhaustiveness


class SongVersion(enum.Enum):
    """Different versions of a song to render."""

    MAIN = enum.auto()
    INSTRUMENTAL = enum.auto()
    INSTRUMENTAL_DJ = enum.auto()
    ACAPPELLA = enum.auto()
    STEMS = enum.auto()

    def name_for_project_dir(self, project_dir: Path) -> str:
        """Name of the project for the given song version."""
        project_name = project_dir.name
        if self is SongVersion.MAIN:
            return project_name
        elif self is SongVersion.INSTRUMENTAL:
            return f"{project_name} (Instrumental)"
        elif self is SongVersion.INSTRUMENTAL_DJ:
            return f"{project_name} (DJ Instrumental)"
        elif self is SongVersion.ACAPPELLA:
            return f"{project_name} (A Cappella)"
        elif self is SongVersion.STEMS:
            return f"{project_name} (Stems)"
        else:  # pragma: no cover
            assert_exhaustiveness(self)

    def path_for_project_dir(self, project_dir: Path) -> Path:
        """Path of the rendered file for the given song version."""
        path = project_dir / self.name_for_project_dir(project_dir)
        if self is SongVersion.STEMS:
            return path

        return Path(f"{path}.wav")

    @property
    def pattern(self) -> list[Path]:
        """Reaper directory render pattern for the given song version, if any."""
        if self is SongVersion.STEMS:
            # Roughly create a directory tree matching the tracks and folders in the Reaper project.
            return [Path("$folders $tracknumber - $track")]

        return []
