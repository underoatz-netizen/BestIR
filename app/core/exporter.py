"""Copy selected IR files to a destination folder, resolving name collisions."""
from __future__ import annotations

import shutil
from pathlib import Path


def unique_dest(dest_dir: Path, name: str) -> Path:
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    for i in range(2, 1000):
        dest = dest_dir / f'{stem} ({i}){suffix}'
        if not dest.exists():
            return dest
    raise RuntimeError(f'Could not find a free name for {name}')


def export_files(paths: list[str], dest_dir: str) -> list[str]:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    exported = []
    for src in paths:
        target = unique_dest(dest, Path(src).name)
        shutil.copy2(src, target)
        exported.append(str(target))
    return exported
