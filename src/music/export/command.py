"""Export command."""

import shutil
from pathlib import Path

import click


@click.command("export")
@click.argument(
    "dst_dir",
    type=click.Path(dir_okay=True, file_okay=False, path_type=Path),
)
@click.argument(
    "files",
    nargs=-1,
    required=True,
    type=click.Path(dir_okay=False, exists=True, file_okay=True, path_type=Path),
)
def main(dst_dir: Path, files: list[Path]) -> None:
    """Export the given FILES to the given DST_DIR directory.

    Exports in album order.
    """
    dst_dir.mkdir(exist_ok=True)

    for i, src in enumerate(files):
        dst = dst_dir / f"{i+1:02d} - {src.with_suffix('.wav').name}"
        if dst.exists() and src.stat().st_mtime < dst.stat().st_mtime:
            continue

        shutil.copy2(src, dst)
