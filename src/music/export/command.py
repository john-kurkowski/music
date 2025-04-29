"""Export command."""

import errno
import math
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

    Exports in album order. Maintains file metadata.
    """
    dst_dir.mkdir(exist_ok=True)

    for i, src in enumerate(files):
        dst = dst_dir / f"{i + 1:02d} - {src.with_suffix('.wav').name}"
        if not is_src_newer(src, dst):
            continue

        shutil.copyfile(src, dst)
        try:
            shutil.copystat(src, dst)
        except OSError as oserr:
            copy_success_but_missing_extended_flags = oserr.errno == errno.EINVAL
            if not copy_success_but_missing_extended_flags:
                raise


def is_src_newer(src: Path, dst: Path) -> bool:
    """Return True if the source file is newer than the destination file, or the destination file does not yet exist.

    Allow modification times within 2s of each other. Songs are very unlikely to
    take so little time to render and be this close. Without this tolerance, a
    lower resolution filesystem time will always compare different to a higher
    resolution one. `round` or `math.floor` are insufficient, as the lower
    resolution filesystem timestamps are unpredictable whether they'll go 1s up or
    down.
    """
    if not dst.exists():
        return True

    src_time = src.stat().st_mtime
    dst_time = dst.stat().st_mtime
    return src_time > dst_time and not math.isclose(src_time, dst_time, abs_tol=2.0)
