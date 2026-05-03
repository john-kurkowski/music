"""ReaSamplOmatic5000-specific analyze helpers."""

from collections.abc import Iterator
from pathlib import Path

import rpp  # type: ignore[import-untyped]

from music.commands.analyze.utils import file_refs, plugin_state

_BROKEN_LINK = "⛓️‍💥"


def is_plugin(plugin: rpp.Element) -> bool:
    """Return whether the plugin chunk belongs to ReaSamplOmatic5000."""
    return getattr(plugin, "tag", None) in {"AU", "VST"} and "ReaSamplOmatic5000" in (
        plugin_state.plugin_label(plugin)
    )


def iter_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[str]:
    """Return warnings for missing ReaSamplOmatic5000 sample files."""
    for issue in _iter_sample_issues(project_dir, plugin):
        yield issue.warning(plugin_name, track_number, track_name)


def iter_plugin_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact table warnings for missing ReaSamplOmatic5000 sample files."""
    _ = track_number, track_name, plugin_name
    for issue in _iter_sample_issues(project_dir, plugin):
        yield (_BROKEN_LINK, issue.detail)


def _iter_sample_issues(
    project_dir: Path, plugin: rpp.Element
) -> Iterator[file_refs.PluginFileIssue]:
    decoded = plugin_state.decoded_plugin_state(plugin)
    yield from file_refs.iter_file_issues(
        project_dir, plugin_state.iter_path_like_references(decoded)
    )
