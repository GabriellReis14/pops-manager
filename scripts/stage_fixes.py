"""Prepares a fix pack (POPSUtils) for embedding in a personal build.

    python scripts/stage_fixes.py <POPSUtils folder> <stage folder>

- "POPS Game Fixes", "POPS General Fixes" and "Compatibility_Modes" are copied directly under the stage
  folder: shorter paths, so the frozen app stays under Windows' 260-character path limit.
- Disc image patches (.xdelta/.ppf) are not copied (their names are very long and they are applied by hand
  with a patching tool from the original folder); each folder that had them gets IMAGE_PATCHES.TXT with
  their names, so the app can still warn about them.
- Archives and Windows programs are skipped.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from pops_manager.fixes import IMAGE_PATCH_MARKER, IMAGE_PATCH_SUFFIXES  # noqa: E402
from pops_manager.resources import fix_folders  # noqa: E402

SKIP = {'.zip', '.7z', '.rar', '.exe', '.dll'} | IMAGE_PATCH_SUFFIXES


def stage(utils: Path, dest: Path) -> int:
    folders = fix_folders(utils)
    if dest.exists():
        # the \\?\ prefix lets Windows delete leftovers whose paths exceed 260 characters
        shutil.rmtree('\\\\?\\' + str(dest.resolve()) if sys.platform == 'win32' else dest)
    copied = 0
    for source in (folders.game_fixes, folders.general_fixes, folders.compatibility):
        if source is None:
            continue
        for path in sorted(source.rglob('*')):
            target = dest / source.name / path.relative_to(source)
            if path.is_dir():
                patches = sorted(p.name for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_PATCH_SUFFIXES)
                if patches:
                    target.mkdir(parents=True, exist_ok=True)
                    (target / IMAGE_PATCH_MARKER).write_text('\n'.join(patches) + '\n', encoding='utf-8')
            elif path.suffix.lower() not in SKIP:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                copied += 1
    return copied


if __name__ == '__main__':
    count = stage(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f'{count} fix files staged in {sys.argv[2]}')
