from pathlib import Path
import pytest
from pops_manager import vmc
from pops_manager.core import (Cancelled, Game, MAX_ID_LENGTH, SHORT_ID_LENGTH, Options, clean_slug, clean_title, create_vmcs,
                               install, is_valid_identifier, make_games, plan, plan_vmcs, preview,
                               preview_items, title_cfg, validate)
from pops_manager.resources import (ELF_REL, PAK_REL, SUPPORT_REL, Located, locate, pops_files, support_files)
from conftest import FAKE_ELF

THPS = ["Tony Hawk's Pro Skater", "Tony Hawk's Pro Skater 2", "Tony Hawk's Pro Skater 3", "Tony Hawk's Pro Skater 4"]
BARE = Options(vmc=False, multidisc=False)


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())


# --- Game names / identifiers ---------------------------------------------------------------

@pytest.mark.parametrize('suffix', ['', ' (USA)', ' (Europe) (En,Fr,De)'])
@pytest.mark.parametrize('limit', [SHORT_ID_LENGTH, MAX_ID_LENGTH])
def test_tony_hawk_series_gets_distinct_ids_and_folders(tmp_path, suffix, limit):
    games = make_games([Path(f'{name}{suffix}.VCD') for name in THPS], limit=limit)
    slugs = [g.slug for g in games]
    assert len({s.casefold() for s in slugs}) == 4
    assert slugs[0] == 'Tony_Hawks_Pro_Skater'
    assert [s[-2:] for s in slugs[1:]] == ['_2', '_3', '_4']   # the number is the real title, not a dedupe suffix
    assert [g.title for g in games] == THPS
    folders = {str(plan(tmp_path, g)[1][0].parent).casefold() for g in games}
    vcds = {str(plan(tmp_path, g)[0][0]).casefold() for g in games}
    assert len(folders) == len(vcds) == 4


def test_ids_never_exceed_original_limit():
    names = ['Castlevania - Symphony of the Night', 'Final Fantasy VII (USA) (Disc 1)', 'A' * 80,
             'Spider-Man 2 - Enter Electro', 'Tony Hawk\'s Pro Skater 2'] + [f'Some Very Long Game Title {i}' for i in range(15)]
    games = make_games([Path(f'{n}.VCD') for n in names], limit=SHORT_ID_LENGTH)
    assert all(len(g.slug) <= SHORT_ID_LENGTH and is_valid_identifier(g.slug) for g in games)
    assert len({g.slug.casefold() for g in games}) == len(games)


def test_trailing_numbers_survive_shortening():
    assert clean_slug("Tony Hawk's Pro Skater 2", SHORT_ID_LENGTH) == 'Tony_Hawks_Pro_Skate_2'
    assert clean_slug('Short Name 3') == 'Short_Name_3'


def test_cut_ending_in_similar_digits_still_keeps_real_number():
    # 'Abcdefghij_Klmnopq_11_X_1'[:22] ends in '_11', but the real trailing number is '1'
    slug = clean_slug('Abcdefghij Klmnopq 11 X 1', SHORT_ID_LENGTH)
    assert slug.endswith('_1') and not slug.endswith('_11') and len(slug) <= SHORT_ID_LENGTH


@pytest.mark.parametrize('name, slug', [
    ('Pokémon Edição Ação', 'Pokemon_Edicao_Acao'),
    ('Ação  &  Reação!!', 'Acao_Reacao'),
    ('Tekken 3', 'Tekken_3'),
    ('007 Racing', '007_Racing'),
    ('Crash Bandicoot - Warped', 'Crash_Bandicoot_Warped'),
    ('!!!', 'Game'),
    ('CON', 'CON_Game'),
    ('日本語', 'Game'),
])
def test_special_characters(name, slug):
    assert clean_slug(name) == slug
    assert is_valid_identifier(slug)


@pytest.mark.parametrize('stem, title', [
    ("Tony Hawk's Pro Skater 2 (USA)", "Tony Hawk's Pro Skater 2"),
    ('Legend of Dragoon, The (USA)', 'The Legend of Dragoon'),
    ('Final Fantasy VII (USA) (Disc 1)', 'Final Fantasy VII (Disc 1)'),
    ('Gran_Turismo_2 [SCUS-94455]', 'Gran Turismo 2'),
    ('Pokémon Stadium', 'Pokémon Stadium'),
    ('D2_Fin_Fan_VII', 'Fin Fan VII (Disc 2)'),
])
def test_clean_title(stem, title):
    assert clean_title(stem) == title


def test_duplicate_names_from_different_folders(make_vcd):
    a, b = make_vcd('A/game.VCD'), make_vcd('B/Game.vcd')
    assert [g.slug for g in make_games([a, b])] == ['game', 'Game_2']


def test_dedupe_respects_taken_and_limit():
    long = 'X' * MAX_ID_LENGTH
    games = make_games([Path(f'{long}.VCD')], taken={long.lower()})
    assert games[0].slug == 'X' * (MAX_ID_LENGTH - 2) + '_2'


@pytest.mark.parametrize('slug, ok', [('Abc_1', True), ('', False), ('a b', False), ('a.b', False),
                                      ('A' * MAX_ID_LENGTH, True), ('A' * (MAX_ID_LENGTH + 1), False), ('nul', False)])
def test_identifier_validation(slug, ok):
    assert is_valid_identifier(slug) is ok


# --- Multi-disc names (same convention as the original converter) ----------------------------

def test_multidisc_names_match_original_convention():
    games = make_games([Path(f'Final Fantasy VII (USA) (Disc {n}).bin') for n in (1, 2, 3)]
                       + [Path('Metal Gear Solid (USA) (Disc 1) (Rev 1).cue'), Path('Metal Gear Solid (USA) (Disc 2).cue')],
                       limit=SHORT_ID_LENGTH)
    assert [g.slug for g in games] == ['D1_Fin_Fan_VII', 'D2_Fin_Fan_VII', 'D3_Fin_Fan_VII', 'D1_Met_Gea_Sol', 'D2_Met_Gea_Sol']
    assert games[1].title == 'Final Fantasy VII (Disc 2)'


def test_multidisc_vii_and_viii_do_not_collide():
    games = make_games([Path('Final Fantasy VII (Disc 1).VCD'), Path('Final Fantasy VIII (Disc 1).VCD')], limit=SHORT_ID_LENGTH)
    assert [g.slug for g in games] == ['D1_Fin_Fan_VII', 'D1_Fin_Fan_VIII']


def test_multidisc_same_abbreviation_gets_suffix():
    games = make_games([Path('Final Fantasy (Disc 1).VCD'), Path('Finest Fanfare (Disc 1).VCD')], limit=SHORT_ID_LENGTH)
    assert games[0].slug == 'D1_Fin_Fan' and games[1].slug == 'D1_Fin_Fan_2'


def test_full_names_by_default():
    games = make_games([Path("Tony Hawk's Pro Skater 2 (USA).VCD"), Path('Castlevania - Symphony of the Night (USA).cue'),
                        Path('Final Fantasy VII (USA) (Disc 1).bin'), Path('Final Fantasy VII (USA) (Disc 2).bin')])
    assert [g.slug for g in games] == ['Tony_Hawks_Pro_Skater_2', 'Castlevania_Symphony_of_the_Night',
                                       'D1_Final_Fantasy_VII', 'D2_Final_Fantasy_VII']
    long = make_games([Path('X' * 100 + '.VCD')])[0]
    assert len(long.slug) == MAX_ID_LENGTH and is_valid_identifier(long.slug)


def test_short_names_like_original_converter():
    games = make_games([Path("Tony Hawk's Pro Skater 2 (USA).VCD"), Path('Castlevania - Symphony of the Night (USA).cue')],
                       limit=SHORT_ID_LENGTH)
    assert [g.slug for g in games] == ['Tony_Hawks_Pro_Skate_2', 'Castlevania_Symphony_o']


def test_already_converted_disc_names_are_kept():
    games = make_games([Path('D1_Fin_Fan_VII.VCD'), Path('D2_Fin_Fan_VII.VCD')])
    assert [g.slug for g in games] == ['D1_Fin_Fan_VII', 'D2_Fin_Fan_VII']


# --- Validation -----------------------------------------------------------------------------

def test_single_and_multiple_files_from_different_directories(make_vcd):
    assert make_games([make_vcd('x/One.VCD')])[0].slug == 'One'
    many = make_games([make_vcd('a/b/One.VCD'), make_vcd('c/Two.vcd'), make_vcd('d e f/Três.VCD')])
    assert [g.slug for g in many] == ['One', 'Two', 'Tres']


def test_invalid_paths_are_rejected(tmp_path, elf, usb, make_vcd):
    with pytest.raises(ValueError, match='not found'):
        validate([Game(tmp_path / 'missing.VCD', 'Missing', 'Missing')], usb, elf)
    other = tmp_path / 'game.txt'; other.write_bytes(b'x')
    with pytest.raises(ValueError, match='Unsupported'):
        validate(make_games([other]), usb, elf)
    game = make_games([make_vcd('ok.VCD')])
    with pytest.raises(ValueError, match='destination'):
        validate(game, tmp_path / 'no_usb', elf)
    with pytest.raises(ValueError, match='at least one'):
        validate([], usb, elf)


def test_rejects_wrong_elf(tmp_path, usb, make_vcd):
    games = make_games([make_vcd('ok.VCD')])
    other = tmp_path / 'OTHER.ELF'; other.write_bytes(FAKE_ELF)
    with pytest.raises(ValueError, match='POPSTARTER.ELF'):
        validate(games, usb, other)
    bogus = tmp_path / 'x' / 'POPSTARTER.ELF'; bogus.parent.mkdir(); bogus.write_bytes(b'MZ not an elf' * 3)
    with pytest.raises(ValueError, match='MIPS'):
        validate(games, usb, bogus)


def test_rejects_duplicate_and_invalid_identifiers(elf, usb, make_vcd):
    a, b = make_vcd('a.VCD'), make_vcd('b.VCD')
    with pytest.raises(ValueError, match='Duplicate'):
        validate([Game(a, 'A', 'Same'), Game(b, 'B', 'SAME')], usb, elf)
    with pytest.raises(ValueError, match='Invalid identifier'):
        validate([Game(a, 'A', 'x' * (MAX_ID_LENGTH + 1))], usb, elf)
    with pytest.raises(ValueError, match='Invalid title'):
        validate([Game(a, 'A\nboot=evil', 'A')], usb, elf)


# --- USB export -----------------------------------------------------------------------------

def test_export_layout_matches_original_converter(elf, usb, make_vcd):
    sources = [make_vcd(f'set{i}/{name} (USA).VCD') for i, name in enumerate(THPS)]
    before = {p: p.read_bytes() for p in sources}
    games = make_games(sources)
    result = install(usb, games, elf, options=BARE)
    assert result.done == [0, 1, 2, 3] and not result.failed and len(result.created) == 3 * len(games)
    for game, source in zip(games, sources):
        app = usb / 'APPS' / f'XX.{game.slug}'
        assert sorted(p.name for p in app.iterdir()) == sorted([f'XX.{game.slug}.ELF', 'title.cfg'])
        assert (app / f'XX.{game.slug}.ELF').read_bytes() == FAKE_ELF
        assert (app / 'title.cfg').read_bytes() == f'title={game.title}\r\nboot=XX.{game.slug}.ELF\r\n'.encode()
        assert (usb / 'POPS' / f'{game.slug}.VCD').read_bytes() == before[source]
    assert sorted(p.name for p in usb.iterdir()) == ['APPS', 'POPS']
    assert {p: p.read_bytes() for p in sources} == before     # originals untouched


def test_vmcs_created_like_original_tool(elf, usb, make_vcd):
    game = make_games([make_vcd('Crash.VCD')])[0]
    install(usb, [game], elf)
    for slot in ('SLOT0.VMC', 'SLOT1.VMC'):
        assert (usb / 'POPS' / 'Crash' / slot).read_bytes() == vmc.blank_vmc()


def test_multidisc_files_like_original_tool(elf, usb, make_vcd):
    sources = [make_vcd(f'Final Fantasy VII (USA) (Disc {n}).VCD') for n in (1, 2, 3)]
    install(usb, make_games(sources, limit=SHORT_ID_LENGTH), elf)
    discs = b'D1_Fin_Fan_VII.VCD\r\nD2_Fin_Fan_VII.VCD\r\nD3_Fin_Fan_VII.VCD\r\n'
    for n in (1, 2, 3):
        folder = usb / 'POPS' / f'D{n}_Fin_Fan_VII'
        assert (folder / 'DISCS.TXT').read_bytes() == discs
        assert (folder / 'VMCDIR.TXT').read_bytes() == b'D1_Fin_Fan_VII'
        assert (folder / 'SLOT0.VMC').exists() is (n == 1)


def test_existing_saves_are_kept(elf, usb, make_vcd):
    game = make_games([make_vcd('Crash.VCD')])[0]
    (usb / 'POPS' / 'Crash').mkdir(parents=True)
    (usb / 'POPS' / 'Crash' / 'SLOT0.VMC').write_bytes(b'MY SAVES')
    assert any(i.state == 'kept' for i in preview_items(usb, [game]))
    install(usb, [game], elf)
    assert (usb / 'POPS' / 'Crash' / 'SLOT0.VMC').read_bytes() == b'MY SAVES'
    assert (usb / 'POPS' / 'Crash' / 'SLOT1.VMC').read_bytes() == vmc.blank_vmc()


def test_title_cfg_is_utf8(elf, usb, make_vcd):
    game = make_games([make_vcd('Pokémon Ação.VCD')])[0]
    install(usb, [game], elf)
    assert (usb / 'APPS' / f'XX.{game.slug}' / 'title.cfg').read_bytes().decode('utf-8') == title_cfg(game)


def test_conflicts_detected_before_any_write(elf, usb, make_vcd):
    first, second = make_games([make_vcd('First.VCD'), make_vcd('Second.VCD')])
    (usb / 'POPS').mkdir()
    (usb / 'POPS' / 'Second.VCD').write_bytes(b'user data')
    with pytest.raises(FileExistsError):
        install(usb, [first, second], elf)
    assert files_under(usb) == ['POPS/Second.VCD']
    assert (usb / 'POPS' / 'Second.VCD').read_bytes() == b'user data'


def test_existing_app_folder_is_a_conflict(elf, usb, make_vcd):
    game = make_games([make_vcd('Game.VCD')])[0]
    (usb / 'APPS' / 'XX.Game').mkdir(parents=True)
    with pytest.raises(FileExistsError, match='folder'):
        install(usb, [game], elf)


def test_second_run_refuses_to_overwrite(elf, usb, make_vcd):
    game = make_games([make_vcd('Game.VCD')])[0]
    install(usb, [game], elf)
    with pytest.raises(FileExistsError):
        install(usb, [game], elf)


def test_shared_files_copied_once_and_never_overwritten(tmp_path, elf, usb, make_vcd):
    pak = tmp_path / 'tools' / 'POPS_IOX.PAK'; pak.write_bytes(b'PAK')
    shared = [(pak, Path('POPS/POPS_IOX.PAK'))]
    a, b = make_games([make_vcd('A.VCD'), make_vcd('B.VCD')])
    assert usb / 'POPS' / 'POPS_IOX.PAK' in install(usb, [a], elf, shared).created
    assert 'IDENTICAL' in preview(usb, [b], shared)[0]
    assert usb / 'POPS' / 'POPS_IOX.PAK' not in install(usb, [b], elf, shared).created
    other = tmp_path / 'other' / 'POPS_IOX.PAK'; other.parent.mkdir(); other.write_bytes(b'DIFFERENT')
    c = make_games([make_vcd('C.VCD')])[0]
    assert 'OTHER VERSION' in preview(usb, [c], [(other, Path('POPS/POPS_IOX.PAK'))])[0]
    install(usb, [c], elf, [(other, Path('POPS/POPS_IOX.PAK'))])
    assert (usb / 'POPS' / 'POPS_IOX.PAK').read_bytes() == b'PAK'


def test_missing_shared_file_is_rejected(tmp_path, elf, usb, make_vcd):
    game = make_games([make_vcd('A.VCD')])
    with pytest.raises(ValueError, match='support file'):
        validate(game, usb, elf, [(tmp_path / 'gone.irx', Path('POPSTARTER/gone.irx'))])


def test_failed_game_is_rolled_back_and_others_continue(elf, usb, make_vcd):
    games = make_games([make_vcd('A.VCD', b'a' * 10), make_vcd('B.VCD', b'b' * 10), make_vcd('C.VCD', b'c' * 10)])

    def progress(event):
        if event.game == 1 and event.step == 'copy':
            raise RuntimeError('simulated write error')
    result = install(usb, games, elf, options=BARE, progress=progress)
    assert result.done == [0, 2] and list(result.failed) == [1] and 'simulated' in result.failed[1]
    assert files_under(usb) == ['APPS/XX.A/XX.A.ELF', 'APPS/XX.A/title.cfg', 'APPS/XX.C/XX.C.ELF',
                                'APPS/XX.C/title.cfg', 'POPS/A.VCD', 'POPS/C.VCD']


def test_cancel_keeps_finished_games_and_undoes_current(elf, usb, make_vcd):
    games = make_games([make_vcd('A.VCD'), make_vcd('B.VCD')])

    def progress(event):
        if event.game == 1 and event.step == 'copy':
            raise Cancelled()
    result = install(usb, games, elf, options=BARE, progress=progress)
    assert result.cancelled and result.done == [0]
    assert files_under(usb) == ['APPS/XX.A/XX.A.ELF', 'APPS/XX.A/title.cfg', 'POPS/A.VCD']


def test_progress_events(elf, usb, make_vcd):
    games = make_games([make_vcd('A.VCD', b'a' * 100)])
    events = []
    install(usb, games, elf, progress=events.append)
    copies = [e for e in events if e.step == 'copy']
    assert copies[-1].done == copies[-1].total == 100
    assert events[-1].step == 'done' and events[-1].game == 0


def test_preview_marks_existing(elf, usb, make_vcd):
    game = make_games([make_vcd('Game.VCD')])[0]
    assert not any('[EXISTS' in line for line in preview(usb, [game]))
    install(usb, [game], elf)
    text = '\n'.join(preview(usb, [game]))
    assert text.count('[EXISTS]') == 3 and text.count('[EXISTS, KEPT]') == 2 and 'XX.Game' in text


# --- VMC tool for games already on the device ----------------------------------------------

def test_create_vmcs_for_existing_device_games(usb):
    (usb / 'POPS').mkdir()
    for name in ('Crash', 'D1_Fin_Fan_VII', 'D2_Fin_Fan_VII'):
        (usb / 'POPS' / f'{name}.VCD').write_bytes(b'X')
    (usb / 'POPS' / 'Crash').mkdir(); (usb / 'POPS' / 'Crash' / 'SLOT0.VMC').write_bytes(b'SAVE')
    planned = sorted(p.relative_to(usb).as_posix() for p, _ in plan_vmcs(usb))
    assert planned == ['POPS/Crash/SLOT1.VMC', 'POPS/D1_Fin_Fan_VII/DISCS.TXT', 'POPS/D1_Fin_Fan_VII/SLOT0.VMC',
                       'POPS/D1_Fin_Fan_VII/SLOT1.VMC', 'POPS/D1_Fin_Fan_VII/VMCDIR.TXT',
                       'POPS/D2_Fin_Fan_VII/DISCS.TXT', 'POPS/D2_Fin_Fan_VII/VMCDIR.TXT']
    assert len(create_vmcs(usb)) == 7
    assert (usb / 'POPS' / 'Crash' / 'SLOT0.VMC').read_bytes() == b'SAVE'
    assert plan_vmcs(usb) == []


# --- Resources ------------------------------------------------------------------------------

def test_pops_folder_files(tmp_path):
    folder = tmp_path / 'POPS'; folder.mkdir()
    for name in ('POPS_IOX.PAK', 'CHEATS.TXT', 'IGR_BG.TM2', 'POPSTARTER.ELF', 'PS1_USB_Converter.exe',
                 'libgcc_s_seh-1.dll', 'Game.VCD'):
        (folder / name).write_bytes(b'x')
    (folder / 'Game').mkdir()
    names = [r.name for _, r in pops_files(folder)]
    assert sorted(names) == ['CHEATS.TXT', 'IGR_BG.TM2', 'POPSTARTER.ELF', 'POPS_IOX.PAK']
    assert 'PS1_USB_Converter.exe' in [r.name for _, r in pops_files(folder, include_windows=True)]
    assert all(r.parts[0] == 'POPS' for _, r in pops_files(folder))


def test_support_folder_files(tmp_path):
    folder = tmp_path / 'POPSTARTER'; (folder / 'sub').mkdir(parents=True)
    (folder / 'usbd.irx').write_bytes(b'U'); (folder / 'sub' / 'x.bin').write_bytes(b'X')
    assert [r.as_posix() for _, r in support_files(folder)] == ['POPSTARTER/sub/x.bin', 'POPSTARTER/usbd.irx']
    assert support_files(None) == [] and support_files(tmp_path / 'nope') == []


def test_locate_resources_order(tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    (second / 'POPS').mkdir(parents=True); (second / 'POPS' / 'POPSTARTER.ELF').write_bytes(FAKE_ELF)
    (second / 'POPSTARTER').mkdir()
    dirs = [('bundled', first), ('local', second)]
    assert locate(ELF_REL, dirs=dirs) == Located(second / ELF_REL, 'local')
    assert locate(SUPPORT_REL, folder=True, dirs=dirs).origin == 'local'
    assert locate(PAK_REL, dirs=dirs) == Located(None, 'missing')
    custom = tmp_path / 'mine.ELF'
    assert locate(ELF_REL, custom, dirs=dirs) == Located(custom, 'custom')
    (first / 'POPS').mkdir(parents=True); (first / 'POPS' / 'POPSTARTER.ELF').write_bytes(FAKE_ELF)
    assert locate(ELF_REL, dirs=dirs).origin == 'bundled'


def test_pops_folder_names_upper_case_on_device(tmp_path):
    folder = tmp_path / 'POPS'; folder.mkdir()
    (folder / 'CHEATS.txt').write_bytes(b'$HDTVFIX')
    assert [r.as_posix() for _, r in pops_files(folder)] == ['POPS/CHEATS.TXT']
