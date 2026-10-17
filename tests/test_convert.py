"""Disc image -> VCD conversion, on small synthetic images (header checked field by field)."""
from pathlib import Path
import zipfile
import pytest
from pops_manager import convert
from pops_manager.convert import HEADER_SIZE, SECTOR, SYNC, ConversionError
from pops_manager.core import install, make_games


def data_sectors(n: int, tag: bytes = b'D') -> bytes:
    return b''.join(SYNC + bytes([0, 2, i % 75, 2]) + tag * (SECTOR - 16) for i in range(n))


def audio_sectors(n: int) -> bytes:
    return b'\x11' * (SECTOR * n)


def write_cue(folder: Path, name: str, text: str) -> Path:
    cue = folder / f'{name}.cue'
    cue.write_text(text.strip() + '\n', encoding='utf-8')
    return cue


def header_of(vcd: Path) -> bytes:
    return vcd.read_bytes()[:HEADER_SIZE]


def test_single_data_track(tmp_path):
    (tmp_path / 'g.bin').write_bytes(data_sectors(10))
    cue = write_cue(tmp_path, 'g', 'FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00')
    vcd = convert.to_vcd(cue, tmp_path / 'out')
    h = header_of(vcd)
    assert h[0x00] == 0x41 and h[0x02] == 0xA0 and h[0x07] == 0x01 and h[0x08] == 0x20
    assert h[0x0A] == 0x41 and h[0x0C] == 0xA1 and h[0x11] == 0x01
    assert h[0x14] == 0x41 and h[0x16] == 0xA2 and h[0x1B:0x1E] == bytes([0x00, 0x02, 0x10])   # 10 + 150 frames
    assert h[0x1E:0x28] == bytes([0x41, 0, 0x01, 0, 0, 0, 0, 0x00, 0x02, 0x00])               # INDEX 01 = 00:02:00
    assert h[0x28:0x400] == bytes(0x400 - 0x28)
    assert h[0x400:0x404] == b'kHn\x22'
    assert int.from_bytes(h[0x408:0x40C], 'little') == int.from_bytes(h[0x40C:0x410], 'little') == 10
    assert vcd.read_bytes()[HEADER_SIZE:] == (tmp_path / 'g.bin').read_bytes()
    assert vcd.stat().st_size == convert.probe(cue)


def test_data_plus_audio_tracks(tmp_path):
    (tmp_path / 'g.bin').write_bytes(data_sectors(1000) + audio_sectors(500))
    cue = write_cue(tmp_path, 'g', '''
FILE "g.bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    INDEX 00 00:13:00
    INDEX 01 00:15:00
''')
    h = header_of(convert.to_vcd(cue, tmp_path / 'out'))
    assert h[0x0A] == 0x01 and h[0x11] == 0x02 and h[0x14] == 0x01            # last track: audio, number 2
    assert h[0x1B:0x1E] == bytes([0x00, 0x22, 0x00])                          # 1500 + 150 = 22 s
    assert h[0x28:0x32] == bytes([0x01, 0, 0x02, 0x00, 0x15, 0x00, 0, 0x00, 0x17, 0x00])   # +2 s on both indexes


def test_multi_file_cue_equals_merged_image(tmp_path):
    (tmp_path / 'g (Track 1).bin').write_bytes(data_sectors(900))
    (tmp_path / 'g (Track 2).bin').write_bytes(audio_sectors(400))
    split = write_cue(tmp_path, 'split', '''
FILE "g (Track 1).bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
FILE "g (Track 2).bin" BINARY
  TRACK 02 AUDIO
    INDEX 00 00:00:00
    INDEX 01 00:02:00
''')
    (tmp_path / 'merged.bin').write_bytes(data_sectors(900) + audio_sectors(400))
    merged = write_cue(tmp_path, 'merged', '''
FILE "merged.bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    INDEX 00 00:12:00
    INDEX 01 00:14:00
''')
    assert convert.to_vcd(split, tmp_path / 'a').read_bytes() == convert.to_vcd(merged, tmp_path / 'b').read_bytes()


def test_cdrwin_pregap_inserts_blank_sectors(tmp_path):
    (tmp_path / 'g.bin').write_bytes(data_sectors(100) + audio_sectors(50))
    cue = write_cue(tmp_path, 'g', '''
FILE "g.bin" BINARY
  TRACK 01 MODE2/2352
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    PREGAP 00:02:00
    INDEX 01 00:01:25
''')
    vcd = convert.to_vcd(cue, tmp_path / 'out')
    data = vcd.read_bytes()
    h = data[:HEADER_SIZE]
    assert int.from_bytes(h[0x408:0x40C], 'little') == 150 + 150                 # 150 sectors + 150 padding
    assert h[0x28:0x32] == bytes([0x01, 0, 0x02, 0x00, 0x05, 0x25, 0, 0x00, 0x05, 0x25])   # 100 + 150 + 150 = 400 frames = 00:05:25
    body = data[HEADER_SIZE:]
    assert body[:100 * SECTOR] == data_sectors(100)
    assert body[100 * SECTOR:250 * SECTOR] == bytes(150 * SECTOR)
    assert body[250 * SECTOR:] == audio_sectors(50)
    assert vcd.stat().st_size == convert.probe(cue)


def test_raw_bin_without_cue(tmp_path):
    raw = tmp_path / 'g.bin'; raw.write_bytes(data_sectors(5))
    vcd = convert.to_vcd(raw, tmp_path / 'out')
    assert vcd.read_bytes()[HEADER_SIZE:] == raw.read_bytes()
    iso = tmp_path / 'raw.iso'; iso.write_bytes(data_sectors(5))     # a raw image named .iso is fine
    assert convert.probe(iso) == HEADER_SIZE + 5 * SECTOR


def test_2048_iso_rejected_with_explanation(tmp_path):
    iso = tmp_path / 'g.iso'; iso.write_bytes(bytes(2048 * 20))
    with pytest.raises(ConversionError, match='2048'):
        convert.probe(iso)


@pytest.mark.parametrize('cue_text, message', [
    ('FILE "g.bin" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00', 'not supported'),
    ('FILE "g.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00', 'MODE2/2352'),
    ('FILE "missing.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00', 'not found'),
    ('FILE "g.bin" WAVE\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00', 'BINARY'),
    ('FILE "g.bin" BINARY\n TRACK 01 MODE2/2352', 'INDEX 01'),
])
def test_bad_cues(tmp_path, cue_text, message):
    (tmp_path / 'g.bin').write_bytes(data_sectors(3))
    with pytest.raises(ConversionError, match=message):
        convert.probe(write_cue(tmp_path, 'g', cue_text))


def test_collapse_sources_prefers_cue(tmp_path):
    (tmp_path / 'a.bin').write_bytes(data_sectors(2))
    cue = write_cue(tmp_path, 'a', 'FILE "a.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00')
    lone = tmp_path / 'b.bin'; lone.write_bytes(data_sectors(2))
    assert convert.collapse_sources([tmp_path / 'a.bin', cue, lone]) == [cue, lone]
    assert convert.collapse_sources([tmp_path / 'a.bin']) == [cue]       # sibling cue found


def _cue_and_bin(folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'g.bin').write_bytes(data_sectors(20))
    return write_cue(folder, 'g', 'FILE "g.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00'), folder / 'g.bin'


def test_zip_archive(tmp_path):
    cue, bin_ = _cue_and_bin(tmp_path / 'src')
    archive = tmp_path / 'Game (USA).zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.write(cue, 'Game/g.cue'); z.write(bin_, 'Game/g.bin'); z.writestr('readme.txt', 'hi')
    expected = convert.to_vcd(cue, tmp_path / 'direct').read_bytes()
    events = []
    vcd = convert.to_vcd(archive, tmp_path / 'work', lambda d, t: events.append((d, t)))
    assert vcd.read_bytes() == expected
    assert events[-1][0] == events[-1][1]
    assert convert.probe(archive) == len(expected)


def test_7z_archive(tmp_path):
    py7zr = pytest.importorskip('py7zr')
    cue, bin_ = _cue_and_bin(tmp_path / 'src')
    archive = tmp_path / 'Game.7z'
    with py7zr.SevenZipFile(archive, 'w') as z:
        z.write(cue, 'g.cue'); z.write(bin_, 'g.bin')
    assert convert.to_vcd(archive, tmp_path / 'work').read_bytes() == convert.to_vcd(cue, tmp_path / 'direct').read_bytes()


def test_archive_with_two_discs_rejected(tmp_path):
    archive = tmp_path / 'two.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('a.cue', ''); z.writestr('b.cue', '')
    with pytest.raises(ConversionError, match='2 discs'):
        convert.probe(archive)


def test_install_converts_in_temp_folder(tmp_path, elf, usb):
    cue, _ = _cue_and_bin(tmp_path / 'lib' / 'Crash')
    work = tmp_path / 'work'; work.mkdir()
    game = make_games([cue])[0]
    steps = []
    result = install(usb, [game], elf, progress=lambda e: steps.append(e.step), workdir=work)
    assert result.done == [0]
    assert 'convert' in steps and 'copy' in steps
    vcd = usb / 'POPS' / f'{game.slug}.VCD'
    assert vcd.read_bytes() == convert.to_vcd(cue, tmp_path / 'direct').read_bytes()
    assert list(work.iterdir()) == []                         # temporary files removed
    assert (tmp_path / 'lib' / 'Crash' / 'g.bin').exists()    # source untouched


def _cue_games(tmp_path, count, sectors=200):
    lib = tmp_path / 'lib'; lib.mkdir(exist_ok=True)
    cues = []
    for n in range(count):
        (lib / f'Game {n}.bin').write_bytes(data_sectors(sectors, tag=bytes([65 + n])))
        cues.append(write_cue(lib, f'Game {n}', f'FILE "Game {n}.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00'))
    return make_games(cues)


def test_next_games_convert_while_current_is_copied(tmp_path, elf, usb):
    import threading
    from pops_manager.core import Options
    games = _cue_games(tmp_path, 3)
    second_converting = threading.Event()
    events = []

    def progress(event):
        events.append((event.game, event.step))
        if event.game == 1 and event.step == 'convert':
            second_converting.set()
        if event.game == 0 and event.step == 'copy':
            # the copy of game 0 cannot finish until game 1 is converting: proves they run in parallel
            assert second_converting.wait(30), 'game 1 was not converted in parallel'
    result = install(usb, games, elf, options=Options(workers=2), progress=progress, workdir=tmp_path)
    assert result.done == [0, 1, 2]
    copies = [g for g, step in events if step == 'copy']
    assert copies == sorted(copies)                 # device writes strictly one game after another
    for game in games:
        assert (usb / 'POPS' / f'{game.slug}.VCD').read_bytes()[HEADER_SIZE:] == (game.source.parent / f'{game.source.stem}.bin').read_bytes()


def test_cancel_with_conversions_ahead(tmp_path, elf, usb):
    from pops_manager.core import Cancelled, Options
    games = _cue_games(tmp_path, 4)
    work = tmp_path / 'work'; work.mkdir()

    def progress(event):
        if event.game == 1 and event.step == 'copy':
            raise Cancelled()
    result = install(usb, games, elf, options=Options(workers=3), progress=progress, workdir=work)
    assert result.cancelled and result.done == [0]
    assert sorted(p.name for p in (usb / 'POPS').glob('*.VCD')) == [f'{games[0].slug}.VCD']
    assert list(work.iterdir()) == []               # temporary conversions removed


def test_conversion_workers_limited_by_temp_space(tmp_path, monkeypatch):
    import shutil as sh
    from pops_manager import core
    games = _cue_games(tmp_path, 3, sectors=10)
    assert core._conversion_workers(games, tmp_path, 4) == 3
    monkeypatch.setattr(sh, 'disk_usage', lambda p: sh._ntuple_diskusage(0, 0, 3 * (HEADER_SIZE + 10 * SECTOR) * 2))
    assert core._conversion_workers(games, tmp_path, 4) == 2
    vcds = make_games([tmp_path / 'x.VCD'])
    assert core._conversion_workers(vcds, tmp_path, 4) == 1
