"""Vendor-specific analyze helpers."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import rpp  # type: ignore[import-untyped]

from music.commands.analyze.vendors import sitala
from music.commands.analyze.vendors.cockos import reasamplomatic5000
from music.commands.analyze.vendors.output import arcade
from music.commands.analyze.vendors.spitfire import labs

_WarningIterator = Callable[
    [Path, int, str, str, rpp.Element],
    Iterator[str],
]
_PluginWarningIterator = Callable[
    [Path, int, str, str, rpp.Element],
    Iterator[tuple[str, str]],
]


@dataclass(frozen=True)
class _Analyzer:
    """Function bundle for a vendor-specific analyzer module."""

    is_plugin: Callable[[rpp.Element], bool]
    iter_warnings: _WarningIterator
    iter_plugin_warnings: _PluginWarningIterator


@dataclass(frozen=True)
class _SettingAnalyzer:
    """Function bundle for decoded raw setting overrides."""

    is_plugin: Callable[[rpp.Element], bool]
    decoded_setting: Callable[[rpp.Element], bytes | None]


_ANALYZERS = (
    _Analyzer(arcade.is_plugin, arcade.iter_warnings, arcade.iter_plugin_warnings),
    _Analyzer(
        reasamplomatic5000.is_plugin,
        reasamplomatic5000.iter_warnings,
        reasamplomatic5000.iter_plugin_warnings,
    ),
    _Analyzer(sitala.is_plugin, sitala.iter_warnings, sitala.iter_plugin_warnings),
    _Analyzer(labs.is_plugin, labs.iter_warnings, labs.iter_plugin_warnings),
)
_SETTING_ANALYZERS = (_SettingAnalyzer(arcade.is_plugin, arcade.decoded_setting),)


def decoded_setting(plugin: rpp.Element) -> bytes | None:
    """Return a vendor-normalized decoded setting preview, when available."""
    for analyzer in _SETTING_ANALYZERS:
        if analyzer.is_plugin(plugin):
            setting = analyzer.decoded_setting(plugin)
            if setting is not None:
                return setting
    return None


def iter_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[str]:
    """Return full warning lines from analyzers that understand a plugin."""
    for analyzer in _ANALYZERS:
        if analyzer.is_plugin(plugin):
            yield from analyzer.iter_warnings(
                project_dir, track_number, track_name, plugin_name, plugin
            )


def iter_plugin_warnings(
    project_dir: Path,
    track_number: int,
    track_name: str,
    plugin_name: str,
    plugin: rpp.Element,
) -> Iterator[tuple[str, str]]:
    """Return compact warning cells from analyzers that understand a plugin."""
    for analyzer in _ANALYZERS:
        if analyzer.is_plugin(plugin):
            yield from analyzer.iter_plugin_warnings(
                project_dir, track_number, track_name, plugin_name, plugin
            )
