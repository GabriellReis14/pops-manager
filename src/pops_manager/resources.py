"""Finds the POPStarter support files. They are never part of the public repository or release.

A resources folder mirrors the device root:

    <resources>/POPS/POPSTARTER.ELF   used to create every XX.<ID>.ELF
    <resources>/POPS/...              POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2... copied to <device>/POPS/
    <resources>/POPSTARTER/...        copied as-is to <device>/POPSTARTER/

Search order: user setting > embedded in the exe (personal build) > `resources` next to the exe >
project root (running from source).
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys

POPS_REL = Path('POPS')
ELF_REL = POPS_REL / 'POPSTARTER.ELF'
PAK_REL = POPS_REL / 'POPS_IOX.PAK'
SUPPORT_REL = Path('POPSTARTER')
# Windows programs that usually sit in the POPS folder (the converters and their MinGW DLLs).
# They cannot run on a PS2, so they are skipped unless the user asks for them.
WINDOWS_SUFFIXES = {'.exe', '.dll'}
NEVER_COPY = {'.vcd', '.bin', '.cue', '.iso', '.img', '.zip', '.7z'}   # games are handled separately


@dataclass(frozen=True)
class Located:
    path: Path | None
    origin: str   # 'custom', 'bundled', 'local' or 'missing'


def candidate_dirs() -> list[tuple[str, Path]]:
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        return [('bundled', Path(getattr(sys, '_MEIPASS', exe_dir)) / 'resources'), ('local', exe_dir / 'resources')]
    return [('local', Path(__file__).resolve().parents[2])]


def locate(rel: Path, custom: Path | None = None, *, folder: bool = False,
           dirs: list[tuple[str, Path]] | None = None) -> Located:
    if custom is not None:
        return Located(custom, 'custom')
    for origin, base in candidate_dirs() if dirs is None else dirs:
        path = base / rel
        if path.is_dir() if folder else path.is_file():
            return Located(path, origin)
    return Located(None, 'missing')


# POPStarter r13 Beta (2019/06/05) by krHACKen, redistributed unmodified in the public build (see
# scripts/fetch_popstarter.py). It is the last fallback: the user's own POPSTARTER.ELF always wins.
INCLUDED_ELF = Path(__file__).resolve().parent / 'third_party' / 'POPSTARTER.ELF'
INCLUDED_ELF_SHA256 = '734c813e8e8ec2c6729ec5e15dd46ab696e90deeade8d0b2ca3ad03782781aa1'


def included_elf() -> Path | None:
    return INCLUDED_ELF if INCLUDED_ELF.is_file() else None


def local_dir() -> Path:
    """Where a user is told to put the files: `resources` next to the exe (project root from source)."""
    return candidate_dirs()[-1][1]


def child(folder: Path | None, name: str, *, folder_wanted: bool = False) -> Path | None:
    """`folder/name`, ignoring upper/lower case (POPSTARTER.ELF vs popstarter.elf)."""
    if folder is None or not folder.is_dir():
        return None
    for path in folder.iterdir():
        if path.name.casefold() == name.casefold() and (path.is_dir() if folder_wanted else path.is_file()):
            return path
    return None


def pops_folder_from(chosen: Path) -> Path | None:
    """The POPS folder for a folder the user picked: the folder itself if it has POPSTARTER.ELF or
    POPS_IOX.PAK, or its POPS sub-folder (the user may pick the parent, e.g. the old converter's folder)."""
    def has_files(folder: Path | None) -> bool:
        return bool(child(folder, 'POPSTARTER.ELF') or child(folder, 'POPS_IOX.PAK'))
    if has_files(chosen):
        return chosen
    sub = child(chosen, 'POPS', folder_wanted=True)
    return sub if has_files(sub) else None


def support_files(folder: Path | None) -> list[tuple[Path, Path]]:
    """(source, path relative to the device root) for every file inside the POPSTARTER folder."""
    if folder is None or not folder.is_dir():
        return []
    return [(f, SUPPORT_REL / f.relative_to(folder)) for f in sorted(folder.rglob('*')) if f.is_file()]


def pops_files(folder: Path | None, include_windows: bool = False) -> list[tuple[Path, Path]]:
    """Top-level files of the POPS folder to copy to <device>/POPS/ (no games, no per-game folders)."""
    if folder is None or not folder.is_dir():
        return []
    files = []
    for f in sorted(folder.iterdir()):
        suffix = f.suffix.lower()
        if not f.is_file() or suffix in NEVER_COPY or (suffix in WINDOWS_SUFFIXES and not include_windows):
            continue
        # POPStarter's USB driver is case-sensitive and expects upper-case names (CHEATS.TXT, IGR_BG.TM2)
        files.append((f, POPS_REL / (f.name if suffix in WINDOWS_SUFFIXES else f.name.upper())))
    return files


UTILS_REL = POPS_REL / 'POPSUtils'


@dataclass(frozen=True)
class FixFolders:
    game_fixes: Path | None       # "POPS Game Fixes": one folder per game
    general_fixes: Path | None    # "POPS General Fixes": optional fixes for any game
    compatibility: Path | None    # "Compatibility_Modes": PATCH_1..7.BIN


def fix_folders(utils: Path | None) -> FixFolders:
    """Finds the fix pack folders inside POPSUtils (names compared case-insensitively, any depth)."""
    if utils is None or not utils.is_dir():
        return FixFolders(None, None, None)
    found: dict[str, Path] = {}
    for folder in sorted(p for p in utils.rglob('*') if p.is_dir()):
        key = folder.name.casefold().replace('_', ' ')
        for wanted in ('pops game fixes', 'pops general fixes', 'compatibility modes'):
            if key == wanted and wanted not in found:
                found[wanted] = folder
    if 'pops game fixes' not in found and any(p.is_dir() for p in utils.iterdir()):
        found['pops game fixes'] = utils if not found else None     # a bare folder of game folders
    return FixFolders(found.get('pops game fixes'), found.get('pops general fixes'), found.get('compatibility modes'))
