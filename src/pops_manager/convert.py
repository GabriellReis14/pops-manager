"""PS1 disc images -> POPStarter VCD. Accepts .VCD, .CUE(+BIN), raw .BIN/.ISO/.IMG and .ZIP/.7Z archives.

A VCD is a 1 MiB header (TOC, see vcd_header) followed by the raw 2352-byte sectors of the disc.
Everything is written to a temporary folder; the caller copies the finished VCD.
"""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import zipfile

SECTOR = 2352
HEADER_SIZE = 0x100000
SUPPORTED = {'.vcd', '.cue', '.bin', '.iso', '.img', '.zip', '.7z'}
IMAGE_SUFFIXES = {'.cue', '.bin', '.iso', '.img'}
ARCHIVE_SUFFIXES = {'.zip', '.7z'}
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
Progress = Callable[[int, int], None]


class ConversionError(ValueError):
    pass


def is_vcd(path: Path) -> bool:
    return path.suffix.lower() == '.vcd'


@dataclass
class Track:
    number: int
    mode: str                      # 'MODE2/2352', 'MODE1/2352' or 'AUDIO'
    file: Path
    indexes: dict[int, int] = field(default_factory=dict)   # index -> frame offset inside `file`
    pregap: int = 0                # PREGAP frames (not stored in the BIN)
    postgap: int = 0

    @property
    def audio(self) -> bool:
        return self.mode == 'AUDIO'


def _msf(text: str) -> int:
    m, s, f = (int(x) for x in text.split(':'))
    return (m * 60 + s) * 75 + f


def parse_cue(cue: Path) -> list[Track]:
    tracks: list[Track] = []
    current_file: Path | None = None
    for raw in cue.read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.upper().startswith('REM'):
            continue
        word = line.split()[0].upper()
        if word == 'FILE':
            match = re.match(r'FILE\s+"(.+)"\s+(\w+)\s*$', line, re.I) or re.match(r'FILE\s+(\S+)\s+(\w+)\s*$', line, re.I)
            if not match:
                raise ConversionError(f'Unreadable FILE line in {cue.name}: {line}')
            if match[2].upper() != 'BINARY':
                raise ConversionError(f'{cue.name}: only BINARY files are supported (found {match[2]}).')
            current_file = cue.parent / Path(match[1]).name
        elif word == 'TRACK':
            parts = line.split()
            if current_file is None or len(parts) < 3:
                raise ConversionError(f'Malformed TRACK in {cue.name}: {line}')
            mode = parts[2].upper()
            if mode not in ('MODE2/2352', 'MODE1/2352', 'AUDIO'):
                raise ConversionError(f'{cue.name}: track mode {mode} is not supported (raw 2352-byte sectors required).')
            tracks.append(Track(int(parts[1]), mode, current_file))
        elif word == 'INDEX' and tracks:
            parts = line.split()
            tracks[-1].indexes[int(parts[1])] = _msf(parts[2])
        elif word == 'PREGAP' and tracks:
            tracks[-1].pregap = _msf(line.split()[1])
        elif word == 'POSTGAP' and tracks:
            tracks[-1].postgap = _msf(line.split()[1])
    if not tracks:
        raise ConversionError(f'{cue.name} has no tracks.')
    for track in tracks:
        if 1 not in track.indexes:
            raise ConversionError(f'{cue.name}: track {track.number} has no INDEX 01.')
        if not track.file.is_file():
            raise ConversionError(f'{cue.name}: file not found: {track.file.name}')
    return tracks


def is_raw_image(path: Path) -> bool:
    size = path.stat().st_size
    if size == 0 or size % SECTOR:
        return False
    with path.open('rb') as f:
        return f.read(12) == SYNC


def tracks_for(path: Path) -> list[Track]:
    """Tracks of a .cue or of a raw single-track .bin/.iso/.img (a .cue next to it wins)."""
    suffix = path.suffix.lower()
    if suffix == '.cue':
        return parse_cue(path)
    sibling = next((c for c in path.parent.glob('*.[cC][uU][eE]') if c.stem.casefold() == path.stem.casefold()), None)
    if sibling:
        return parse_cue(sibling)
    if is_raw_image(path):
        return [Track(1, 'MODE2/2352', path, {1: 0})]
    if path.stat().st_size % 2048 == 0:
        raise ConversionError(f'{path.name} is a 2048-byte ISO: PS1 games need a raw 2352-byte image '
                              '(BIN/CUE). Dump or download the game as BIN/CUE.')
    raise ConversionError(f'{path.name} is not a raw 2352-byte PS1 disc image.')


def collapse_sources(paths: list[Path]) -> list[Path]:
    """Keeps one entry per disc: a .bin referenced by a selected (or sibling) .cue is replaced by that .cue."""
    result: list[Path] = []
    referenced: set[str] = set()
    for path in paths:
        if path.suffix.lower() == '.cue':
            try:
                referenced |= {str(t.file).casefold() for t in parse_cue(path)}
            except ConversionError:
                pass
    for path in paths:
        if path.suffix.lower() == '.bin':
            if str(path).casefold() in referenced:
                continue
            sibling = next((c for c in path.parent.glob('*.[cC][uU][eE]') if c.stem.casefold() == path.stem.casefold()), None)
            if sibling:
                path = sibling
        if all(str(path).casefold() != str(p).casefold() for p in result):
            result.append(path)
    return result


# --- archives --------------------------------------------------------------------------------

def _archive_names(path: Path) -> list[tuple[str, int]]:
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as z:
            return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
    try:
        import py7zr
    except ImportError as error:
        raise ConversionError('7z support needs the py7zr package (pip install py7zr).') from error
    with py7zr.SevenZipFile(path) as z:
        return [(i.filename, i.uncompressed) for i in z.list() if not i.is_directory]


def _image_members(path: Path) -> list[tuple[str, int]]:
    members = [(n, s) for n, s in _archive_names(path) if Path(n).suffix.lower() in IMAGE_SUFFIXES]
    cues = [n for n, _ in members if n.lower().endswith('.cue')]
    if len(cues) > 1:
        raise ConversionError(f'{path.name} contains {len(cues)} discs; extract it and add each .cue separately.')
    if not members:
        raise ConversionError(f'{path.name} contains no .cue/.bin/.iso image.')
    return members


def extract(path: Path, dest: Path, progress: Progress | None = None) -> Path:
    """Extracts the disc image files of an archive; returns the .cue (or the single image)."""
    members = _image_members(path)
    dest.mkdir(parents=True, exist_ok=True)
    total = sum(s for _, s in members) or 1
    done = 0
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as z:
            for name, _ in members:
                target = dest / Path(name).name
                with z.open(name) as inp, target.open('xb') as out:
                    while chunk := inp.read(4 * 1024 * 1024):
                        out.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
    else:
        import py7zr
        with py7zr.SevenZipFile(path) as z:
            z.extract(path=dest / '_7z', targets=[n for n, _ in members])
        for name, size in members:
            shutil.move(str(dest / '_7z' / name), dest / Path(name).name)
            done += size
            if progress:
                progress(done, total)
        shutil.rmtree(dest / '_7z', ignore_errors=True)
    cues = list(dest.glob('*.[cC][uU][eE]'))
    if cues:
        return cues[0]
    images = [dest / Path(n).name for n, _ in members]
    if len(images) > 1:
        raise ConversionError(f'{path.name} has several images and no .cue.')
    return images[0]


# --- probing / conversion --------------------------------------------------------------------

def probe(path: Path) -> int:
    """Validates a source without converting it; returns the estimated VCD size in bytes."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ConversionError(f'Unsupported file type: {path.name}')
    if suffix == '.vcd':
        return path.stat().st_size
    if suffix in ARCHIVE_SUFFIXES:
        return HEADER_SIZE + sum(s for n, s in _image_members(path) if not n.lower().endswith('.cue'))
    return HEADER_SIZE + layout(tracks_for(path)).sectors * SECTOR


def to_vcd(path: Path, workdir: Path, progress: Progress | None = None) -> Path:
    """Converts `path` into `workdir/<stem>.VCD` and returns it."""
    workdir.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in ARCHIVE_SUFFIXES:
        def half(done, total):          # extraction = first half of the bar
            if progress:
                progress(done, total * 2)
        image = extract(path, workdir / 'extracted', half)
        out = to_vcd(image, workdir, (lambda d, t: progress(t + d, t * 2)) if progress else None)
        shutil.rmtree(workdir / 'extracted', ignore_errors=True)
        return out
    tracks = tracks_for(path)
    out = workdir / f'{path.stem}.VCD'
    write_vcd(tracks, out, progress)
    return out


# --- VCD writing (CUE2POPS v2.0 layout) ------------------------------------------------------
# Header (1 MiB, zero-filled): A0/A1/A2 TOC points at 0x00/0x0A/0x14, one 10-byte entry per track
# from 0x1E (control, 0, track BCD, INDEX 00 MSF, 0, INDEX 01 MSF; all MSF +2 s for the lead-in),
# "kHn" + format version byte at 0x400, sector count twice (uint32 LE) at 0x408 and 0x40C. Then the raw
# 2352-byte sectors. A CDRWIN-style cue (exactly one PREGAP, no POSTGAP) gets 150 blank sectors
# inserted before the first audio track and its later tracks shifted by another 2 s, like CUE2POPS.

LEAD_IN = 150
# 0x22 (format v2.2) like PSXVCD; byte-identical to its VCDs, which are proven on hardware.
# CUE2POPS v2.0 writes 0x20 and the layout is otherwise the same.
_SIGNATURE = b'kHn"'


def _bcd(n: int) -> int:
    return (n // 10) << 4 | n % 10


def _bcd_msf(frames: int) -> bytes:
    m, rest = divmod(frames, 75 * 60)
    s, f = divmod(rest, 75)
    if m > 99:
        raise ConversionError('Disc image is too long for a CD table of contents.')
    return bytes([_bcd(m), _bcd(s), _bcd(f)])


@dataclass
class Layout:
    """Tracks with absolute frame positions in the VCD body (multi-file cues are joined in order)."""
    files: list[Path]
    file_frames: list[int]
    tracks: list[Track]
    absolute: list[tuple[int, int]]    # per track: (INDEX 00, INDEX 01) absolute frames, without lead-in
    padding_at: int | None             # body frame where 150 blank sectors are inserted (CDRWIN fix)
    sectors: int                       # sectors written to the body (incl. padding)


def layout(tracks: list[Track]) -> Layout:
    if tracks[0].number != 1 or tracks[0].mode != 'MODE2/2352':
        raise ConversionError('Track 01 must be MODE2/2352 (PlayStation data track).')
    pregaps = sum(1 for t in tracks if t.pregap)
    postgaps = sum(1 for t in tracks if t.postgap)
    if postgaps or pregaps > 1:
        raise ConversionError('Unusual cue sheet (several PREGAP/POSTGAP commands) is not supported.')
    files: list[Path] = []
    for track in tracks:
        if track.file not in files:
            files.append(track.file)
    file_frames, offsets, position = [], {}, 0
    for f in files:
        size = f.stat().st_size
        if size % SECTOR:
            raise ConversionError(f'{f.name}: size is not a multiple of {SECTOR} bytes.')
        offsets[f] = position
        file_frames.append(size // SECTOR)
        position += size // SECTOR
    absolute = []
    for track in tracks:
        base = offsets[track.file]
        index1 = base + track.indexes[1]
        index0 = base + track.indexes.get(0, track.indexes[1])
        absolute.append((index0, index1))
    padding_at = None
    if pregaps == 1:                  # CDRWIN fix
        first_audio = next((i for i, t in enumerate(tracks) if t.audio), None)
        if first_audio is not None:
            padding_at = absolute[first_audio][0]
        absolute = [a if i == 0 else (a[0] + LEAD_IN, a[1] + LEAD_IN) for i, a in enumerate(absolute)]
    return Layout(files, file_frames, tracks, absolute, padding_at, position + (LEAD_IN if pregaps else 0))


def vcd_header(lay: Layout) -> bytes:
    header = bytearray(HEADER_SIZE)
    last = lay.tracks[-1]
    last_ctrl = 0x01 if last.audio else 0x41
    header[0x00] = 0x41; header[0x02] = 0xA0; header[0x07] = 0x01; header[0x08] = 0x20
    header[0x0A] = last_ctrl; header[0x0C] = 0xA1; header[0x11] = _bcd(last.number)
    header[0x14] = last_ctrl; header[0x16] = 0xA2
    header[0x1B:0x1E] = _bcd_msf(lay.sectors + LEAD_IN)
    for n, (track, (index0, index1)) in enumerate(zip(lay.tracks, lay.absolute)):
        entry = 0x1E + n * 10
        header[entry] = 0x01 if track.audio else 0x41
        header[entry + 2] = _bcd(track.number)
        header[entry + 3:entry + 6] = _bcd_msf(0 if n == 0 else index0 + LEAD_IN)
        header[entry + 7:entry + 10] = _bcd_msf(index1 + LEAD_IN)
    header[0x400:0x404] = _SIGNATURE
    header[0x408:0x40C] = lay.sectors.to_bytes(4, 'little')
    header[0x40C:0x410] = lay.sectors.to_bytes(4, 'little')
    return bytes(header)


def write_vcd(tracks: list[Track], out: Path, progress: Progress | None = None) -> None:
    lay = layout(tracks)
    total = lay.sectors * SECTOR
    done = 0
    try:
        with out.open('xb') as dest:
            dest.write(vcd_header(lay))
            position = 0                       # body frame
            for f in lay.files:
                with f.open('rb') as src:
                    while chunk := src.read(SECTOR * 1792):          # ~4 MiB, whole sectors
                        frames = len(chunk) // SECTOR
                        if lay.padding_at is not None and position <= lay.padding_at < position + frames:
                            cut = (lay.padding_at - position) * SECTOR
                            dest.write(chunk[:cut]); dest.write(bytes(LEAD_IN * SECTOR)); dest.write(chunk[cut:])
                            done += LEAD_IN * SECTOR
                        else:
                            dest.write(chunk)
                        position += frames
                        done += len(chunk)
                        if progress:
                            progress(done, total)
    except BaseException:
        out.unlink(missing_ok=True)
        raise
