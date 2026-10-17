"""USB POPStarter/OPL Apps file planner and installer. No third-party binaries bundled.

Layout reproduced from PS1_USB_Converter.exe v1.0 (observed by running it on dummy VCDs):

    APPS/XX.<ID>/XX.<ID>.ELF   byte-identical copy of POPSTARTER.ELF
    APPS/XX.<ID>/title.cfg     "title=<name>\\r\\nboot=XX.<ID>.ELF\\r\\n"
    POPS/<ID>.VCD              the original renames in place; we copy (or convert first)

Per-game folder, as "VMC and MultiDisc Creator" v1.0 does it (see vmc.py); existing files are kept:

    POPS/<ID>/SLOT0.VMC, SLOT1.VMC, DISCS.TXT, VMCDIR.TXT

Shared files, copied only when missing: the user's POPS folder (POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2...)
and POPSTARTER/ support folder.

POPStarter finds the VCD from its own ELF name (XX.<ID>.ELF -> mass:/POPS/<ID>.VCD),
so <ID> must be identical in both places.
"""
from __future__ import annotations
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import tempfile
import threading
import unicodedata
from pops_manager import convert, vmc
from pops_manager.copyfile import copy_file

APPS_DIR = 'APPS'
POPS_DIR = 'POPS'
ELF_PREFIX = 'XX.'
PAK_NAME = 'POPS_IOX.PAK'
# Identifier length. The original converter cuts at 22 characters (SHORT_ID_LENGTH, kept as an option),
# but POPStarter accepts longer names: a 23-character VCD boots, and its docs allow 85-character names in
# DISCS.TXT. 48 is a conservative maximum that keeps full titles readable.
MAX_ID_LENGTH = 48
SHORT_ID_LENGTH = 22
_ID_RE = re.compile(rf'[A-Za-z0-9_]{{1,{MAX_ID_LENGTH}}}')
_TAIL_RE = re.compile(r'^(\d+|[IVXLCDM]+)$')
_WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}
_DISC_RE = re.compile(r'\((Disc\s*(\d+))\)', re.I)
KEEP_KINDS = {'VMC', 'DISCS', 'VMCDIR', 'FIX'}   # per-game folder: existing files (saves!) are kept
SharedFile = tuple[Path, Path]                # (source, path relative to the device root)


class Cancelled(Exception):
    """Raised by a progress callback to stop the whole installation."""


@dataclass(frozen=True)
class Game:
    source: Path
    title: str
    slug: str
    fixes: tuple[tuple[Path, str], ...] = ()     # (file, name in POPS/<ID>/): CHEATS.TXT, PATCH_n.BIN, TROJAN_n.BIN


@dataclass(frozen=True)
class Options:
    vmc: bool = True          # create blank SLOT0/SLOT1.VMC
    multidisc: bool = True    # DISCS.TXT/VMCDIR.TXT for D<n>_ games
    workers: int = 3          # images converted in parallel, ahead of the (sequential) device copy


@dataclass(frozen=True)
class Progress:
    game: int | None          # index in games; None = shared files
    step: str                 # 'shared', 'convert', 'copy', 'done', 'error'
    done: int = 0
    total: int = 0
    message: str = ''


@dataclass
class InstallResult:
    created: list[Path] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)
    done: list[int] = field(default_factory=list)
    cancelled: bool = False
    vcds: dict[int, Path] = field(default_factory=dict)     # game index -> VCD written on the device


# --- names -----------------------------------------------------------------------------------

def clean_title(stem: str) -> str:
    """OPL display name: drops (Region)/[tags], keeps (Disc N), 'Name, The' -> 'The Name'."""
    info = vmc.disc_info(stem)
    if info:                                      # already converted multi-disc name: D2_Fin_Fan_VII
        return f'{info[1].replace("_", " ")} (Disc {info[0]})'
    text = stem.replace('_', ' ')
    disc = _DISC_RE.search(text)
    text = re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' -')
    match = re.fullmatch(r'(.*?),\s*The\b\s*(.*)', text, re.I)
    if match:
        text = f'The {match[1]} {match[2]}'.strip()
    if disc:
        text = f'{text} (Disc {int(disc[2])})'
    return text or stem.strip() or 'Game'


def is_valid_identifier(slug: str) -> bool:
    return bool(_ID_RE.fullmatch(slug)) and slug.upper() not in _WINDOWS_RESERVED


def _split_tail(words: list[str]) -> tuple[list[str], list[str]]:
    """Separates trailing sequel numbers / roman numerals / 'Disc N' from the rest."""
    words, tail = list(words), []
    while words and _TAIL_RE.match(words[-1]) and len(tail) < 2:
        tail.insert(0, words.pop())
    if words and tail and words[-1].casefold() == 'disc':
        tail.insert(0, words.pop())
    return words, tail


def _abbreviate(words: list[str], limit: int) -> str:
    """Joins words with '_' within limit, shortening words but keeping the trailing numbers."""
    words, tail = _split_tail(words)
    joined = '_'.join(words + tail)
    longest = max((len(w) for w in words), default=0)
    for size in range(longest - 1, 2, -1):
        if len(joined) <= limit:
            break
        joined = '_'.join([w if _TAIL_RE.match(w) else w[:size] for w in words] + tail)
    return joined[:limit].strip('_')


def disc_number(stem: str) -> int | None:
    info = vmc.disc_info(stem)
    if info:
        return info[0]
    match = _DISC_RE.search(stem)
    return int(match[2]) if match else None


def id_text(stem: str) -> str:
    """Text the identifier is built from: like the original, file name minus (Region)/[tags]/(Disc N)."""
    info = vmc.disc_info(stem)
    if info:
        return info[1]
    return re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', stem.replace('_', ' '))


def _words(text: str) -> list[str]:
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"['`´’]", '', text)
    return [w for w in re.split(r'[^A-Za-z0-9]+', text) if w]


def _not_reserved(slug: str) -> str:
    slug = slug or 'Game'
    return f'{slug}_Game' if slug.upper() in _WINDOWS_RESERVED else slug


def clean_slug(text: str, limit: int = MAX_ID_LENGTH) -> str:
    """Original converter rule (keep [A-Za-z0-9_], cut at `limit`), unless the cut would drop the
    sequel number/disc - the cause of the Tony Hawk's Pro Skater 2/3/4 collisions in the original."""
    words = _words(text)
    full = '_'.join(words)
    tail = '_'.join(_split_tail(words)[1])
    slug = full[:limit].strip('_')
    if len(full) > limit and tail and not (slug == tail or slug.endswith(f'_{tail}')):
        slug = _abbreviate(words, limit)
    return _not_reserved(slug)


def disc_base(text: str, limit: int) -> str:
    """Multi-disc base like the original converter: 3 letters per word ('Fin_Fan_VII').
    Numbers and roman numerals stay whole, so FF VII and FF VIII do not collide."""
    words = [w if _TAIL_RE.match(w) else w[:3] for w in _words(text)]
    return '_'.join(words)[:limit].strip('_') or 'Game'


def unique_slug(base: str, taken: set[str], limit: int = MAX_ID_LENGTH) -> str:
    slug, i = base, 2
    while slug.casefold() in taken:
        suffix = f'_{i}'
        slug = base[:limit - len(suffix)].rstrip('_') + suffix
        i += 1
    return slug


def make_games(paths: list[Path], taken: set[str] | None = None, limit: int = MAX_ID_LENGTH) -> list[Game]:
    """Creates games with identifiers unique among themselves and `taken` (casefolded).
    Discs of the same game ('X (Disc 1)', 'X (Disc 2)') share one base: D1_<base>, D2_<base>.
    `limit=SHORT_ID_LENGTH` reproduces the original converter's short names (3-letter words for discs)."""
    short = limit <= SHORT_ID_LENGTH
    games = []
    slugs = {s.casefold() for s in taken or ()}
    bases: dict[str, str] = {}                     # game title without disc -> chosen base
    for path in paths:
        title = clean_title(path.stem)
        disc = disc_number(path.stem)
        if disc is None:
            slug = unique_slug(clean_slug(id_text(path.stem), limit), slugs, limit)
        else:
            prefix = f'D{disc}_'
            key = re.sub(r'\s*\(Disc \d+\)$', '', title).casefold()
            if key not in bases:
                base = (disc_base(id_text(path.stem), limit - len(prefix)) if short
                        else clean_slug(id_text(path.stem), limit - len(prefix)))
                taken_bases = {s.split('_', 1)[1] for s in slugs if vmc.disc_info(s)} | set(bases.values())
                taken_bases |= {s for s in slugs}
                candidate, i = base, 2
                while candidate.casefold() in {b.casefold() for b in taken_bases}:
                    candidate = base[:limit - len(prefix) - len(f'_{i}')].rstrip('_') + f'_{i}'
                    i += 1
                bases[key] = candidate
            slug = unique_slug(_not_reserved(prefix + bases[key]), slugs, limit)
        slugs.add(slug.casefold())
        games.append(Game(path, title, slug))
    return games


# --- layout ----------------------------------------------------------------------------------

def app_dir(root: Path, game: Game) -> Path:
    return root / APPS_DIR / f'{ELF_PREFIX}{game.slug}'


def game_dir(root: Path, game: Game) -> Path:
    return root / POPS_DIR / game.slug


def title_cfg(game: Game) -> str:
    return f'title={game.title}\r\nboot={ELF_PREFIX}{game.slug}.ELF\r\n'


def disc_group(game: Game, games: Sequence[Game], root: Path | None = None) -> list[str]:
    """All discs of the game's multi-disc set: this batch plus VCDs already on the device."""
    info = vmc.disc_info(game.slug)
    if not info:
        return []
    slugs = [g.slug for g in games]
    if root is not None and (root / POPS_DIR).is_dir():
        slugs += [p.stem for p in (root / POPS_DIR).glob('D*_*.[vV][cC][dD]')]
    return vmc.multidisc_groups(list(dict.fromkeys(slugs))).get(info[1].casefold(), [game.slug])


def plan(root: Path, game: Game, options: Options = Options(), discs: list[str] | None = None) -> list[tuple[Path, str]]:
    """Files of one game. `discs`: its multi-disc set (see disc_group); None = single disc."""
    app, folder = app_dir(root, game), game_dir(root, game)
    entries = [
        (root / POPS_DIR / f'{game.slug}.VCD', 'VCD'),
        (app / f'{ELF_PREFIX}{game.slug}.ELF', 'ELF'),
        (app / 'title.cfg', 'CFG'),
    ]
    multi = bool(options.multidisc and discs)
    if options.vmc and (not multi or game.slug == discs[0]):
        entries += [(folder / name, 'VMC') for name in vmc.VMC_SLOTS]
    if multi:
        entries += [(folder / 'DISCS.TXT', 'DISCS'), (folder / 'VMCDIR.TXT', 'VMCDIR')]
    entries += [(folder / name, 'FIX') for _, name in game.fixes]
    return entries


def generated_content(game: Game, kind: str, discs: list[str] | None) -> bytes:
    if kind == 'CFG':
        return title_cfg(game).encode('utf-8')
    if kind == 'VMC':
        return vmc.blank_vmc()
    if kind == 'DISCS':
        return vmc.discs_txt(discs or [game.slug]).encode('ascii')
    if kind == 'VMCDIR':
        return vmc.vmcdir_txt(discs or [game.slug]).encode('ascii')
    raise ValueError(kind)


def _same_file_content(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open('rb') as fa, b.open('rb') as fb:
        while chunk := fa.read(1024 * 1024):
            if chunk != fb.read(len(chunk)):
                return False
    return True


def shared_state(root: Path, source: Path, rel: Path) -> str:
    """'new' (will be copied), 'same' or 'different'. Existing files are always kept."""
    target = root / rel
    if not target.exists():
        return 'new'
    return 'same' if target.is_file() and source.is_file() and _same_file_content(source, target) else 'different'


@dataclass(frozen=True)
class PreviewItem:
    rel: Path
    kind: str
    state: str     # 'new', 'exists' (conflict), 'kept' (existing kept), 'same', 'different'
    game: int | None = None


def preview_items(root: Path, games: list[Game], shared: Sequence[SharedFile] = (),
                  options: Options = Options()) -> list[PreviewItem]:
    items = []
    for source, rel in shared:
        items.append(PreviewItem(rel, 'SHARED', shared_state(root, source, rel)))
    for index, game in enumerate(games):
        for target, kind in plan(root, game, options, disc_group(game, games, root)):
            state = 'new' if not target.exists() else 'kept' if kind in KEEP_KINDS else 'exists'
            items.append(PreviewItem(target.relative_to(root), kind, state, index))
    return items


_STATE_LABEL = {'new': '', 'exists': '  [EXISTS]', 'kept': '  [EXISTS, KEPT]',
                'same': '  [IDENTICAL, KEPT]', 'different': '  [OTHER VERSION ON DEVICE, KEPT]'}


def preview(root: Path, games: list[Game], shared: Sequence[SharedFile] = (), options: Options = Options()) -> list[str]:
    lines = []
    current = -1
    for item in preview_items(root, games, shared, options):
        if item.game is not None and item.game != current:
            current = item.game
            lines.append(f'[{games[current].title}]  ({games[current].source})')
        prefix = f'  {item.kind}' if item.game is not None else 'SHARED'
        lines.append(f'{prefix}: {item.rel}{_STATE_LABEL[item.state]}')
    return lines


# --- validation / installation ---------------------------------------------------------------

def is_ps2_elf(path: Path) -> bool:
    """Checks the ELF header: 32-bit, little-endian, MIPS (what POPSTARTER.ELF is)."""
    with path.open('rb') as f:
        header = f.read(20)
    return len(header) == 20 and header[:6] == b'\x7fELF\x01\x01' and header[18:20] == b'\x08\x00'


def validate(games: list[Game], root: Path, elf: Path, shared: Sequence[SharedFile] = (),
             options: Options = Options()) -> int:
    """Checks everything before writing. Returns the estimated number of bytes to write."""
    if not games:
        raise ValueError('Select at least one game.')
    if not root.is_dir():
        raise ValueError('The destination must be an existing directory.')
    if not elf.is_file() or elf.name.upper() != 'POPSTARTER.ELF':
        raise ValueError('Select the POPSTARTER.ELF file.')
    if not is_ps2_elf(elf):
        raise ValueError(f'{elf} is not a PS2 (MIPS) ELF executable.')
    for source, _ in shared:
        if not source.is_file():
            raise ValueError(f'Missing support file: {source}')
    seen = set()
    needed = 0
    for game in games:
        if not game.source.is_file():
            raise ValueError(f'File not found: {game.source}')
        if not is_valid_identifier(game.slug):
            raise ValueError(f'Invalid identifier "{game.slug}": use 1-{MAX_ID_LENGTH} letters, digits or underscores.')
        if not game.title.strip() or any(c in game.title for c in '\r\n'):
            raise ValueError(f'Invalid title for {game.source.name}.')
        for source, name in game.fixes:
            if not source.is_file() or not name or '/' in name or '\\' in name:
                raise ValueError(f'Missing fix file for {game.title}: {source}')
        key = game.slug.casefold()
        if key in seen:
            raise ValueError(f'Duplicate game identifier: {game.slug}')
        seen.add(key)
        needed += convert.probe(game.source) + elf.stat().st_size + 2 * vmc.VMC_SIZE + 16384
    for game in games:
        for target, kind in plan(root, game, options, disc_group(game, games, root)):
            if target.exists() and kind not in KEEP_KINDS:
                raise FileExistsError(f'Refusing to overwrite: {target}')
        if app_dir(root, game).exists():
            raise FileExistsError(f'Refusing to reuse existing folder: {app_dir(root, game)}')
    needed += sum(s.stat().st_size + 4096 for s, r in shared if shared_state(root, s, r) == 'new')
    free = shutil.disk_usage(root).free
    if needed > free:
        raise OSError(f'Not enough free space: {needed // 2**20} MiB needed, {free // 2**20} MiB free.')
    return needed


class _Transaction:
    """Tracks created files/folders so a failed step can be undone."""

    def __init__(self):
        self.files: list[Path] = []
        self.dirs: list[Path] = []

    def mkdir(self, directory: Path) -> None:
        if directory.exists():
            return
        self.mkdir(directory.parent)
        directory.mkdir()
        self.dirs.append(directory)

    def copy(self, source: Path, dest: Path, progress=None) -> None:
        self.mkdir(dest.parent)
        self.files.append(dest)
        copy_file(source, dest, progress)

    def write(self, dest: Path, data: bytes) -> None:
        self.mkdir(dest.parent)
        with dest.open('xb') as out:
            self.files.append(dest)
            out.write(data)

    def rollback(self) -> None:
        for item in reversed(self.files):
            item.unlink(missing_ok=True)
        for directory in reversed(self.dirs):
            try:
                directory.rmdir()
            except OSError:
                pass


def install(root: Path, games: list[Game], elf: Path, shared: Sequence[SharedFile] = (),
            options: Options = Options(), progress: Callable[[Progress], None] | None = None,
            workdir: Path | None = None) -> InstallResult:
    """Copies/converts only; existing files are never overwritten.

    Shared files are copied first (all or nothing). Then each game is installed on its own: if a game
    fails, only its files are removed and the next game continues (see InstallResult.failed).
    Images are converted to VCD in a temporary folder that is deleted at the end.
    `progress` receives Progress events; raising Cancelled inside it stops everything: the game in
    progress is rolled back, finished games are kept and the result has `cancelled=True`.
    """
    validate(games, root, elf, shared, options)
    emit = progress or (lambda event: None)
    result = InstallResult()

    pending = [(s, r) for s, r in shared if shared_state(root, s, r) == 'new']
    transaction = _Transaction()
    try:
        for n, (source, rel) in enumerate(pending, start=1):
            emit(Progress(None, 'shared', n, len(pending), str(rel)))
            transaction.copy(source, root / rel)
    except Cancelled:
        transaction.rollback()
        result.cancelled = True
        return result
    except BaseException:
        transaction.rollback()
        raise
    result.created += transaction.files

    temp = Path(tempfile.mkdtemp(prefix='pops-manager-', dir=workdir))
    stop = threading.Event()
    workers = _conversion_workers(games, temp, options.workers)

    def prepare(index: int, game: Game) -> Path:
        """Runs in a worker thread: converts the image while earlier games are being copied."""
        def converting(done: int, total: int) -> None:
            if stop.is_set():
                raise Cancelled()
            emit(Progress(index, 'convert', done, total))
        if stop.is_set():
            raise Cancelled()
        if convert.is_vcd(game.source):
            return game.source
        return convert.to_vcd(game.source, temp / game.slug, converting)

    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='convert')
    futures: dict[int, object] = {}

    def schedule(upto: int) -> None:
        for j in range(len(futures), min(upto, len(games))):
            futures[j] = pool.submit(prepare, j, games[j])

    try:
        for index, game in enumerate(games):
            schedule(index + workers + 1)              # keep a few conversions ahead of the copy
            transaction = _Transaction()
            try:
                vcd = futures[index].result()
                discs = disc_group(game, games, root)
                fixes = dict((name, source) for source, name in game.fixes)
                for target, kind in plan(root, game, options, discs):
                    if kind == 'VCD':
                        # one VCD at a time: parallel writes would fragment the files on the device
                        transaction.copy(vcd, target, lambda d, t, i=index: emit(Progress(i, 'copy', d, t)))
                        result.vcds[index] = target
                    elif kind == 'ELF':
                        transaction.copy(elf, target)
                    elif kind in KEEP_KINDS and target.exists():
                        continue
                    elif kind == 'FIX':
                        transaction.copy(fixes[target.name], target)
                    else:
                        transaction.write(target, generated_content(game, kind, discs))
                result.created += transaction.files
                result.done.append(index)
                emit(Progress(index, 'done'))
            except Cancelled:
                transaction.rollback()
                result.vcds.pop(index, None)
                result.cancelled = True
                break
            except Exception as error:
                transaction.rollback()
                result.vcds.pop(index, None)
                result.failed[index] = str(error) or type(error).__name__
                emit(Progress(index, 'error', message=result.failed[index]))
            finally:
                shutil.rmtree(temp / game.slug, ignore_errors=True)
    finally:
        stop.set()
        pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(temp, ignore_errors=True)
    return result


def _conversion_workers(games: list[Game], temp: Path, wanted: int) -> int:
    """Parallel conversions, limited by the free space of the temporary folder (an archive needs
    room for the extracted image plus the VCD)."""
    images = [g for g in games if not convert.is_vcd(g.source)]
    if not images:
        return 1
    biggest = max(convert.probe(g.source) for g in images) * 2
    free = shutil.disk_usage(temp).free
    return max(1, min(wanted, len(images), free // max(biggest, 1) - 1))


def device_games(root: Path) -> list[Game]:
    """Games already on the device (POPS/<ID>.VCD)."""
    folder = root / POPS_DIR
    if not folder.is_dir():
        return []
    vcds = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.vcd')
    return [Game(p, clean_title(p.stem), p.stem) for p in vcds]


def plan_vmcs(root: Path, options: Options = Options()) -> list[tuple[Path, bytes]]:
    """Missing VMC / DISCS.TXT / VMCDIR.TXT for the VCDs already on the device, like
    "VMC and MultiDisc Creator" (which skips games whose files already exist)."""
    games = device_games(root)
    missing = []
    for game in games:
        discs = disc_group(game, games, root)
        for target, kind in plan(root, game, options, discs):
            if kind in KEEP_KINDS and not target.exists():
                missing.append((target, generated_content(game, kind, discs)))
    return missing


def create_vmcs(root: Path, options: Options = Options()) -> list[Path]:
    """Creates the missing per-game files on the device; all or nothing."""
    transaction = _Transaction()
    try:
        for target, data in plan_vmcs(root, options):
            transaction.write(target, data)
    except BaseException:
        transaction.rollback()
        raise
    return transaction.files
