"""Streaming package archive helpers; upstream license timestamps may predate ZIP's epoch."""
from pathlib import Path
import zipfile


def portable_zip(source: Path, target: Path):
    boundary=source.resolve()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,strict_timestamps=False) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_symlink() or not path.resolve().is_relative_to(boundary):
                raise ValueError('Package input contains a link or escaped path')
            if path.is_file():archive.write(path,path.relative_to(source))
