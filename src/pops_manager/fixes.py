"""Per-game POPStarter fixes (CHEATS.TXT, PATCH_n.BIN, TROJAN_n.BIN) from a fix pack such as
"Hugopocked POPStarter Fixes". The files go to the game's VMC folder, POPS/<ID>/.

Pack layout (POPS Game Fixes):
    <Game Title> [All versions]/CHEATS.TXT, PATCH_1.BIN, TROJAN_0.BIN     for every version
    <Game Title>/<Game Title (USA)>/TROJAN_0.BIN                           for one version (region, languages, [v1.1])
    <Game Title>/<Game Title (USA)>/16-9/TROJAN_0.BIN                      optional variant chosen by the user
    *.xdelta / *.ppf                                                       patches for the disc image itself

Matching uses the game file name (No-Intro style: "Crash Team Racing (USA)"). Only the game folder and the
best matching version folder are applied automatically; variants are offered in the interface.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata

FIX_NAME_RE = re.compile(r'^(CHEATS\.TXT|PATCH_\d+\.BIN|TROJAN_\d+\.BIN)$', re.I)
REGION_CHEATS_RE = re.compile(r'^(?:(?P<a>.+?)\s+Ver\s+CHEATS|CHEATS\s+(?P<b>.+?))\.TXT$', re.I)
IMAGE_PATCH_SUFFIXES = {'.xdelta', '.ppf'}
# In a personal build the patches themselves are not embedded (see scripts/stage_fixes.py); this file lists them.
IMAGE_PATCH_MARKER = 'IMAGE_PATCHES.TXT'
_GROUP_RE = re.compile(r'\(([^)]*)\)|\[([^\]]*)\]|\{[^}]*\}')
_VERSION_RE = re.compile(r'^v\d+(\.\d+)*$', re.I)
_IGNORED_TAGS = {'all versions'}


def base_key(name: str) -> str:
    """'Tony Hawk's Pro Skater [All versions]' and 'Tony Hawk's Pro Skater (USA)' -> 'tonyhawksproskater'."""
    text = _GROUP_RE.sub(' ', name)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower().replace('&', ' and ')
    text = re.sub(r"['`´’]", '', text)
    text = re.sub(r',\s*the\b', ' ', text)
    text = re.sub(r'^\s*the\s+', '', text)
    return re.sub(r'[^a-z0-9]+', '', text)


def tags(name: str) -> set[str]:
    """Contents of (...) and [...] groups, lower case: {'usa', 'en,fr,de', 'v1.1', 'disc 1'}."""
    found = set()
    for paren, bracket in _GROUP_RE.findall(name):
        tag = (paren or bracket).strip().lower()
        if tag and tag not in _IGNORED_TAGS:
            found.add(tag)
    return found


def _version_score(folder_tags: set[str], game_tags: set[str]) -> int | None:
    """Version folders: [v1.0] [v1.1] means "either". A game without a version tag is v1.0."""
    folder_versions = {t for t in folder_tags if _VERSION_RE.match(t)}
    game_versions = {t for t in game_tags if _VERSION_RE.match(t)} or {'v1.0'}
    if not folder_versions:
        return 0
    return 1 if folder_versions & game_versions else None


def match_score(folder_name: str, game_name: str) -> int | None:
    """None if the folder is for another version; otherwise how many of its tags the game has."""
    folder_tags, game_tags = tags(folder_name), tags(game_name)
    version = _version_score(folder_tags, game_tags)
    if version is None:
        return None
    others = {t for t in folder_tags if not _VERSION_RE.match(t)}
    if not others <= game_tags:
        return None
    return len(others) + version


def fix_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and FIX_NAME_RE.match(p.name))


def is_image_patch(path: Path) -> bool:
    return path.is_file() and (path.suffix.lower() in IMAGE_PATCH_SUFFIXES or path.name.upper() == IMAGE_PATCH_MARKER)


def _has_fixes(folder: Path) -> bool:
    """Fix files, regional cheats or image patches anywhere inside the folder."""
    return any(p.is_file() and (FIX_NAME_RE.match(p.name) or REGION_CHEATS_RE.match(p.name) or is_image_patch(p))
               for p in folder.rglob('*'))


@dataclass
class FixMatch:
    game_folder: Path                       # e.g. ".../Crash Team Racing"
    version_folder: Path | None = None      # e.g. ".../Crash Team Racing/Crash Team Racing (USA)"
    files: list[tuple[Path, str]] = field(default_factory=list)   # applied automatically
    variants: list[Path] = field(default_factory=list)            # folders the user may choose
    image_patches: list[Path] = field(default_factory=list)       # .xdelta/.ppf: patch the image yourself
    notes: list[Path] = field(default_factory=list)               # other text files (instructions)
    version_unknown: bool = False                                 # version folders exist, none matched

    @property
    def label(self) -> str:
        return self.game_folder.name if self.version_folder is None else f'{self.game_folder.name} / {self.version_folder.name}'


class FixPack:
    """Index of a "POPS Game Fixes" folder."""

    def __init__(self, root: Path):
        self.root = root
        self.games: dict[str, list[Path]] = {}       # base key -> game folders
        self.versions: dict[str, list[tuple[Path, Path]]] = {}   # base key -> (game folder, version folder)
        if not root.is_dir():
            return
        for game in sorted(p for p in root.iterdir() if p.is_dir()):
            self.games.setdefault(base_key(game.name), []).append(game)
            for sub in sorted(p for p in game.iterdir() if p.is_dir()):
                self.versions.setdefault(base_key(sub.name), []).append((game, sub))

    def __len__(self) -> int:
        return sum(len(v) for v in self.games.values())

    def match(self, game_name: str) -> FixMatch | None:
        """Fixes for a game file name such as 'Crash Team Racing (USA)' (extension removed)."""
        key = base_key(game_name)
        candidates = []                                   # (score, game folder, version folder)
        for game, sub in self.versions.get(key, []):
            score = match_score(sub.name, game_name)
            if score is not None:
                candidates.append((score, game, sub))
        for game in self.games.get(key, []):          # version folders may use a shorter/other title
            for sub in (p for p in game.iterdir() if p.is_dir()):
                score = match_score(sub.name, game_name)
                if score is not None and tags(sub.name) and _has_fixes(sub):
                    candidates.append((score, game, sub))
        candidates = list(dict.fromkeys(candidates))
        best = max((c[0] for c in candidates), default=None)
        top = [c for c in candidates if c[0] == best]
        if len({c[2] for c in top}) == 1:
            _, game, version = top[0]
        elif self.games.get(key):
            game, version = self.games[key][0], None
        else:
            return None
        found = FixMatch(game, version)
        chosen: dict[str, Path] = {p.name.upper(): p for p in fix_files(game)}
        if version is not None:
            chosen.update({p.name.upper(): p for p in fix_files(version)})
        scope = [game] + ([version] if version else [])
        game_tags = tags(game_name)
        if 'CHEATS.TXT' not in chosen or version is None:
            for folder in scope:
                for p in folder.iterdir():
                    m = REGION_CHEATS_RE.match(p.name) if p.is_file() else None
                    if m and (m['a'] or m['b']).strip().lower() in game_tags:
                        chosen['CHEATS.TXT'] = p
        found.files = sorted(((p, name) for name, p in chosen.items()), key=lambda f: f[1])
        # optional sub-folders (16-9 / 4-3, Arcade / Simulation...); without a known version, all of them
        found.variants = sorted(p for p in (version or game).rglob('*') if p.is_dir() and fix_files(p))
        if version is None:
            found.version_unknown = any(p.is_dir() and _has_fixes(p) for p in game.iterdir())
        for folder in scope:
            for p in folder.iterdir():
                if is_image_patch(p):
                    found.image_patches.append(p)
                elif p.is_file() and p.suffix.lower() == '.txt' and not FIX_NAME_RE.match(p.name) and not REGION_CHEATS_RE.match(p.name):
                    found.notes.append(p)
        if version is not None:
            found.image_patches += [p for p in version.rglob('*') if is_image_patch(p) and p not in found.image_patches]
        if not found.files and not found.variants and not found.image_patches:
            return None
        return found


def folder_files(folder: Path) -> list[tuple[Path, str]]:
    """Fix files of a folder chosen by the user (variant, compatibility mode, general fix)."""
    return [(p, p.name.upper()) for p in fix_files(folder)]


def general_fixes(root: Path | None) -> list[Path]:
    """Leaf folders of "POPS General Fixes" / "Compatibility_Modes" that contain fix files."""
    if root is None or not root.is_dir():
        return []
    return sorted(p for p in root.rglob('*') if p.is_dir() and fix_files(p))


def compatibility_modes(root: Path | None) -> list[Path]:
    """PATCH_1.BIN ... PATCH_7.BIN of the "Compatibility_Modes" folder (use one at a time)."""
    if root is None or not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_file() and re.match(r'^PATCH_\d+\.BIN$', p.name, re.I)),
                  key=lambda p: int(re.findall(r'\d+', p.name)[0]))
