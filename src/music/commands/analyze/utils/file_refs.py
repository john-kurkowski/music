"""Helpers for validating file references saved in projects and plugin state."""

import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginFileIssue:
    """A plugin-owned file reference that is missing or non-portable."""

    saved_ref: str
    resolved_path: Path
    missing: bool

    @property
    def detail(self) -> str:
        """Return a compact display label for table warnings."""
        return self.resolved_path.name or self.saved_ref

    def warning(self, plugin_name: str, track_number: int, track_name: str) -> str:
        """Render the full stdout warning for a plugin file issue."""
        prefix = f'Plugin "{plugin_name}" on track {track_number} "{track_name}"'
        if self.missing:
            return f"{prefix} references missing sample: {self.saved_ref}"
        return (
            f"{prefix} references a file outside the project folder: "
            f"{self.resolved_path}"
        )


def iter_file_issues(
    project_dir: Path, file_refs: Iterator[str]
) -> Iterator[PluginFileIssue]:
    """Yield missing or external file issues for saved plugin references."""
    seen: set[tuple[str, Path]] = set()
    for saved_ref in file_refs:
        resolved_path = resolve_file_reference(project_dir, saved_ref)
        key = (saved_ref, resolved_path)
        if key in seen:
            continue
        seen.add(key)

        missing = not resolved_path.exists()
        if missing:
            yield PluginFileIssue(saved_ref, resolved_path, missing=True)
        elif not path_is_relative_to(resolved_path, project_dir):
            yield PluginFileIssue(saved_ref, resolved_path, missing=False)


def resolve_file_reference(project_dir: Path, saved_ref: str) -> Path:
    """Resolve saved plugin file references against the project directory."""
    path = _path_from_file_reference(saved_ref)
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve(strict=False)


def path_is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether a resolved path is within a resolved parent directory."""
    try:
        path.relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _path_from_file_reference(saved_ref: str) -> Path:
    ref = saved_ref.strip()
    if ref.startswith("file://:home:/"):
        return Path.home() / urllib.parse.unquote(ref.removeprefix("file://:home:/"))

    parsed = urllib.parse.urlparse(ref)
    if parsed.scheme == "file":
        path = urllib.parse.unquote(parsed.path)
        return Path(path)

    return Path(urllib.parse.unquote(ref)).expanduser()
