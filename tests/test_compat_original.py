"""Side-by-side comparison with the original PS1_USB_Converter.exe (Windows only, opt-in).

    $env:POPS_ORIGINAL_DIR = 'C:\\path\\to\\folder\\with\\PS1_USB_Converter.exe'
    pytest tests/test_compat_original.py -v -s

The folder must also contain POPSTARTER.ELF and the converter's DLLs. Everything runs in a
temporary directory with 1-byte dummy VCDs; nothing in that folder is modified.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import pytest
from pops_manager.core import SHORT_ID_LENGTH, install, make_games

ORIGINAL = Path(os.environ.get('POPS_ORIGINAL_DIR', '')) if os.environ.get('POPS_ORIGINAL_DIR') else None
pytestmark = pytest.mark.skipif(not (sys.platform == 'win32' and ORIGINAL and (ORIGINAL / 'PS1_USB_Converter.exe').is_file()),
                                reason='set POPS_ORIGINAL_DIR to a folder with PS1_USB_Converter.exe (Windows)')

# ASCII names only: the original drops accented letters and writes title.cfg in the ANSI code page.
NAMES = ["Tony Hawk's Pro Skater (USA)", "Tony Hawk's Pro Skater 2 (USA)", "Tony Hawk's Pro Skater 3 (USA)",
         "Tony Hawk's Pro Skater 4 (USA)", 'Legend of Dragoon, The (USA)', 'Crash Bandicoot - Warped',
         'Castlevania - Symphony of the Night (USA)', 'Tekken 3 (Europe)', 'Spyro the Dragon', 'Street Fighter Alpha 3']


def run_original(sandbox: Path) -> Path:
    pops = sandbox / 'POPS'
    pops.mkdir(parents=True)
    for item in ORIGINAL.iterdir():
        if item.suffix.lower() in {'.exe', '.dll'} or item.name.upper() == 'POPSTARTER.ELF':
            shutil.copy2(item, pops / item.name)
    for name in NAMES:
        (pops / f'{name}.VCD').write_bytes(b'X')
    subprocess.run([str(pops / 'PS1_USB_Converter.exe')], cwd=pops, input=b'\n', capture_output=True, timeout=120, check=False)
    return sandbox


def normalize_cfg(data: bytes) -> bytes:
    return re.sub(rb' +\r\n', b'\r\n', data)   # the original leaves a trailing space after "(USA)" removal


def test_output_matches_original(tmp_path):
    original = run_original(tmp_path / 'original')
    source_dir = tmp_path / 'library'; source_dir.mkdir()
    sources = [source_dir / f'{n}.VCD' for n in NAMES]
    for s in sources:
        s.write_bytes(b'X')
    ours = tmp_path / 'ours'; ours.mkdir()
    games = make_games(sources, limit=SHORT_ID_LENGTH)
    install(ours, games, ORIGINAL / 'POPSTARTER.ELF')

    original_ids = {p.name[3:] for p in (original / 'APPS').iterdir()}
    print(f'\n{"file":44} {"original":24} {"POPS Manager":24}')
    for name, game in zip(NAMES, games):
        print(f'{name:44} {(game.slug if game.slug in original_ids else "-- skipped/other --"):24} {game.slug:24}')
    matched = [g for g in games if g.slug in original_ids]
    assert len(matched) == len(original_ids), f'original produced IDs we do not: {original_ids - {g.slug for g in games}}'
    for game in matched:
        rel_app = Path('APPS') / f'XX.{game.slug}'
        for rel in [rel_app / f'XX.{game.slug}.ELF', rel_app / 'title.cfg', Path('POPS') / f'{game.slug}.VCD']:
            assert (original / rel).is_file() and (ours / rel).is_file(), rel
        assert (original / rel_app / f'XX.{game.slug}.ELF').read_bytes() == (ours / rel_app / f'XX.{game.slug}.ELF').read_bytes()
        assert normalize_cfg((original / rel_app / 'title.cfg').read_bytes()) == (ours / rel_app / 'title.cfg').read_bytes()
    # the known bug: the original skips THPS 2/3/4; we must create all of them, distinct
    assert len({g.slug.casefold() for g in games}) == len(NAMES)


VMC_TOOL = 'VMC and MultiDisc Creator.exe'


@pytest.mark.skipif(not (ORIGINAL and (ORIGINAL / VMC_TOOL).is_file()), reason=f'needs {VMC_TOOL} in POPS_ORIGINAL_DIR')
def test_vmc_and_multidisc_match_original(tmp_path):
    from pops_manager.core import create_vmcs
    names = ['Crash_Bandicoot_Warped', 'D1_Fin_Fan_VII', 'D2_Fin_Fan_VII', 'D3_Fin_Fan_VII', 'D1_Met_Gea_Sol', 'D2_Met_Gea_Sol']
    original, ours = tmp_path / 'original' / 'POPS', tmp_path / 'ours' / 'POPS'
    for folder in (original, ours):
        folder.mkdir(parents=True)
        for name in names:
            (folder / f'{name}.VCD').write_bytes(b'X')
    shutil.copy2(ORIGINAL / VMC_TOOL, original / VMC_TOOL)
    # its final "Press any key" reads the console, not stdin: stop it once the work is reported done
    proc = subprocess.Popen([str(original / VMC_TOOL)], cwd=original, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for line in proc.stdout:
            if b'Process completed' in line:
                break
    finally:
        proc.kill(); proc.wait(30)
    shutil.rmtree(original / 'VMC_Resource', ignore_errors=True)    # the tool's own extraction folder
    (original / VMC_TOOL).unlink()
    create_vmcs(ours.parent)

    def tree(folder):
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    assert tree(ours) == tree(original)
