"""Fix pack matching and installation, on a small synthetic pack shaped like "Hugopocked POPStarter Fixes"."""
from pathlib import Path
import pytest
from pops_manager import fixes
from pops_manager.core import Options, install, make_games
from pops_manager.resources import fix_folders
from conftest import FAKE_ELF  # noqa: F401  (fixture module)


def write(path: Path, data: bytes = b'x') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def pack_root(tmp_path) -> Path:
    utils = tmp_path / 'POPSUtils'
    root = utils / 'Hugopocked POPStarter Fixes (2023-08-11)' / 'POPS Game Fixes'
    write(root / "Tony Hawk's Pro Skater 2 [All versions]" / 'CHEATS.TXT', b'$SAFEMODE')
    write(root / "Tony Hawk's Pro Skater 2 [All versions]" / 'PATCH_1.BIN')
    write(root / "Tony Hawk's Pro Skater 2 [All versions]" / 'TROJAN_0.BIN')
    write(root / 'Crash Team Racing' / 'Crash Team Racing (USA)' / 'TROJAN_0.BIN', b'usa')
    write(root / 'Crash Team Racing' / 'Crash Team Racing (USA)' / 'leeme.txt')
    write(root / 'Crash Team Racing' / 'Crash Team Racing (Europe) (En,Fr,De,Es,It)' / 'TROJAN_0.BIN', b'eur')
    write(root / 'Crash Team Racing' / 'CHEATS Europe.TXT', b'eu cheats')
    write(root / 'Final Fantasy VII' / 'Final Fantasy VII (USA)' / 'CHEATS.TXT')
    write(root / 'Final Fantasy VII' / 'Final Fantasy VII (USA)' / '16-9' / 'TROJAN_0.BIN', b'wide')
    write(root / 'Final Fantasy VII' / 'Final Fantasy VII (USA)' / '4-3' / 'TROJAN_0.BIN', b'4:3')
    write(root / 'Oddworld Abe\'s Oddysee' / 'Oddworld Abe\'s Oddysee (USA) [v1.0]' / 'TROJAN_0.BIN', b'v10')
    write(root / 'Oddworld Abe\'s Oddysee' / 'Oddworld Abe\'s Oddysee (USA) [v1.1] [v1.2]' / 'TROJAN_0.BIN', b'v11')
    write(root / 'Digimon World 2003' / 'Digimon World 3 (USA)' / 'PATCH_6.BIN')
    write(root / 'Jade Cocoon Story of the Tamamayu' / 'CHEATS.TXT')
    write(root / 'Jade Cocoon Story of the Tamamayu' / 'Jade Cocoon (USA)' / 'Jade Cocoon (USA) {Fix}.xdelta')
    write(root / 'Tekken 3 [All versions]' / 'CHEATS.TXT', b'all')
    write(root / 'Tekken 3 [All versions]' / 'USA Ver CHEATS.TXT', b'usa')
    general = utils / 'Hugopocked POPStarter Fixes (2023-08-11)' / 'POPS General Fixes'
    write(general / 'GPU Dithering Off' / 'TROJAN_9.BIN')
    write(general / 'CPU Overclock' / 'CPU_Clock+10' / 'TROJAN_2.BIN')
    for n in (1, 2, 3):
        write(utils / 'Compatibility_Modes' / f'PATCH_{n}.BIN')
    write(utils / 'Compatibility_Modes' / 'README.TXT')
    return utils


@pytest.fixture
def pack(pack_root) -> fixes.FixPack:
    return fixes.FixPack(fix_folders(pack_root).game_fixes)


def names(match):
    return [name for _, name in match.files]


def test_fix_folders_found(pack_root):
    found = fix_folders(pack_root)
    assert found.game_fixes.name == 'POPS Game Fixes'
    assert found.general_fixes.name == 'POPS General Fixes'
    assert found.compatibility.name == 'Compatibility_Modes'
    assert [p.name for p in fixes.compatibility_modes(found.compatibility)] == ['PATCH_1.BIN', 'PATCH_2.BIN', 'PATCH_3.BIN']
    assert [p.name for p in fixes.general_fixes(found.general_fixes)] == ['CPU_Clock+10', 'GPU Dithering Off']


@pytest.mark.parametrize('name, key', [
    ("Tony Hawk's Pro Skater 2 [All versions]", 'tonyhawksproskater2'),
    ("Tony Hawk's Pro Skater 2 (USA)", 'tonyhawksproskater2'),
    ('Legend of Dragoon, The (USA) (Disc 1)', 'legendofdragoon'),
    ('Castlevania - Symphony of the Night (USA)', 'castlevaniasymphonyofthenight'),
    ('Pokémon Stadium', 'pokemonstadium'),
])
def test_base_key(name, key):
    assert fixes.base_key(name) == key


def test_all_versions_folder(pack):
    match = pack.match("Tony Hawk's Pro Skater 2 (USA)")
    assert names(match) == ['CHEATS.TXT', 'PATCH_1.BIN', 'TROJAN_0.BIN'] and match.version_folder is None


def test_region_folders(pack):
    usa = pack.match('Crash Team Racing (USA)')
    eur = pack.match('Crash Team Racing (Europe) (En,Fr,De,Es,It)')
    assert usa.version_folder.name == 'Crash Team Racing (USA)' and usa.files[0][0].read_bytes() == b'usa'
    assert [n.name for n in usa.notes] == ['leeme.txt']
    assert eur.version_folder.name.startswith('Crash Team Racing (Europe)')
    assert dict((n, p.read_bytes()) for p, n in eur.files) == {'CHEATS.TXT': b'eu cheats', 'TROJAN_0.BIN': b'eur'}


def test_unknown_version_offers_choices(pack):
    match = pack.match('Crash Team Racing (Japan)')
    assert match.version_unknown and match.files == [] and len(match.variants) == 2


def test_variants_are_offered_not_applied(pack):
    match = pack.match('Final Fantasy VII (USA) (Disc 1)')
    assert names(match) == ['CHEATS.TXT'] and [v.name for v in match.variants] == ['16-9', '4-3']


@pytest.mark.parametrize('game, data', [("Oddworld - Abe's Oddysee (USA)", b'v10'),
                                        ("Oddworld - Abe's Oddysee (USA) (v1.2)", b'v11')])
def test_version_tags(pack, game, data):
    assert pack.match(game).files[0][0].read_bytes() == data


def test_version_folder_with_other_title_and_image_patches(pack):
    assert names(pack.match('Digimon World 3 (USA)')) == ['PATCH_6.BIN']
    jade = pack.match('Jade Cocoon - Story of the Tamamayu (USA)')
    assert names(jade) == ['CHEATS.TXT'] and len(jade.image_patches) == 1


def test_regional_cheats_file(pack):
    usa = dict((n, p.read_bytes()) for p, n in pack.match('Tekken 3 (USA)').files)
    eur = dict((n, p.read_bytes()) for p, n in pack.match('Tekken 3 (Europe)').files)
    assert usa['CHEATS.TXT'] == b'usa' and eur['CHEATS.TXT'] == b'all'


def test_no_fix(pack):
    assert pack.match('Crash Bandicoot (USA)') is None


def test_fixes_installed_and_never_overwritten(tmp_path, elf, usb, make_vcd, pack):
    game = make_games([make_vcd("Tony Hawk's Pro Skater 2 (USA).VCD")])[0]
    from dataclasses import replace
    game = replace(game, fixes=tuple(pack.match(game.source.stem).files))
    folder = usb / 'POPS' / game.slug
    write(folder / 'CHEATS.TXT', b'mine')
    install(usb, [game], elf)
    assert sorted(p.name for p in folder.iterdir()) == ['CHEATS.TXT', 'PATCH_1.BIN', 'SLOT0.VMC', 'SLOT1.VMC', 'TROJAN_0.BIN']
    assert (folder / 'CHEATS.TXT').read_bytes() == b'mine'


def test_fixes_go_to_every_disc(tmp_path, elf, usb, make_vcd):
    from dataclasses import replace
    fix = write(tmp_path / 'fix' / 'TROJAN_0.BIN')
    games = [replace(g, fixes=((fix, 'TROJAN_0.BIN'),)) for g in
             make_games([make_vcd(f'Final Fantasy VII (USA) (Disc {n}).VCD') for n in (1, 2)])]
    install(usb, games, elf, options=Options())
    assert all((usb / 'POPS' / g.slug / 'TROJAN_0.BIN').exists() for g in games)


def test_stage_for_build_keeps_matches_and_patch_warnings(tmp_path, pack_root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('stage_fixes', Path(__file__).resolve().parents[1] / 'scripts' / 'stage_fixes.py')
    stage_fixes = importlib.util.module_from_spec(spec); spec.loader.exec_module(stage_fixes)
    write(pack_root / 'Compatibility_Modes' / 'tool.zip')
    staged = tmp_path / 'stage' / 'POPSUtils'
    assert stage_fixes.stage(pack_root, staged) > 0
    assert sorted(p.name for p in staged.iterdir()) == ['Compatibility_Modes', 'POPS Game Fixes', 'POPS General Fixes']
    assert not list(staged.rglob('*.xdelta')) and not list(staged.rglob('*.zip'))
    pack = fixes.FixPack(fix_folders(staged).game_fixes)
    jade = pack.match('Jade Cocoon - Story of the Tamamayu (USA)')
    assert names(jade) == ['CHEATS.TXT'] and [p.name for p in jade.image_patches] == ['IMAGE_PATCHES.TXT']
    assert names(pack.match('Crash Team Racing (USA)')) == ['TROJAN_0.BIN']
