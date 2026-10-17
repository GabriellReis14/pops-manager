"""Headless GUI tests (Qt offscreen platform). They do not replace a manual check."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtCore = pytest.importorskip('PySide6.QtCore')
from pops_manager import main as gui, resources, i18n  # noqa: E402
from conftest import FAKE_ELF  # noqa: E402
from test_convert import data_sectors, write_cue  # noqa: E402

PT = i18n.T['pt']


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def resources_dir(tmp_path, monkeypatch):
    """Fake 'embedded' resources; the user's real files are never used by the tests."""
    base = tmp_path / 'bundled'
    (base / 'POPS').mkdir(parents=True); (base / 'POPSTARTER').mkdir()
    (base / 'POPS' / 'POPSTARTER.ELF').write_bytes(FAKE_ELF)
    (base / 'POPS' / 'POPS_IOX.PAK').write_bytes(b'PAK')
    (base / 'POPS' / 'CHEATS.TXT').write_bytes(b'$HDTVFIX')
    (base / 'POPS' / 'PS1_USB_Converter.exe').write_bytes(b'MZ')
    (base / 'POPSTARTER' / 'usbd.irx').write_bytes(b'USBD')
    monkeypatch.setattr(resources, 'candidate_dirs', lambda: [('bundled', base)])
    return base


@pytest.fixture
def settings(tmp_path):
    return QtCore.QSettings(str(tmp_path / 'settings.ini'), QtCore.QSettings.Format.IniFormat)


@pytest.fixture
def window(app, settings, resources_dir):
    w = gui.Window(settings)
    yield w
    w.close()


def run_install(window, app, monkeypatch, timeout_ms=20000):
    """Clicks Prepare PS2 with dialogs answered automatically; waits for the worker thread."""
    messages = []
    monkeypatch.setattr(gui.QMessageBox, 'question', lambda *a: gui.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(gui.QMessageBox, 'information', lambda *a: messages.append(('info', a[2])))
    monkeypatch.setattr(gui.QMessageBox, 'warning', lambda *a: messages.append(('warning', a[2])))
    monkeypatch.setattr(gui.QMessageBox, 'critical', lambda *a: messages.append(('critical', a[2])))
    window.prepare()
    timer = QtCore.QElapsedTimer(); timer.start()
    while window.busy() and timer.elapsed() < timeout_ms:
        app.processEvents(); QtCore.QThread.msleep(10)
    assert not window.busy(), 'installation did not finish'
    return messages


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())


def top_items(tree) -> dict:
    return {tree.topLevelItem(i).text(0): tree.topLevelItem(i) for i in range(tree.topLevelItemCount())}


def test_translations_have_same_keys():
    keys = set(i18n.T['pt'])
    assert all(set(table) == keys for table in i18n.T.values())
    assert set(i18n.T) == set(i18n.LANGUAGES) == {'pt', 'en', 'es'}


@pytest.mark.parametrize('index, lang', list(enumerate(i18n.LANGUAGES)))
def test_language_switch(window, index, lang):
    window.language_box.setCurrentIndex(index)
    assert window.add_button.text() == i18n.T[lang]['add']
    assert window.table.horizontalHeaderItem(4).text() == i18n.T[lang]['status']
    assert window.tools_menu.title() == i18n.T[lang]['tools_menu']


def test_qt_standard_buttons_translated(window):
    window.language_box.setCurrentIndex(0)
    assert window.qt_translator.isEmpty() is False, 'qtbase_pt_BR.qm not found'


def test_add_dedupes_and_keeps_edits(window, make_vcd):
    a, b, c = make_vcd('x/One.VCD'), make_vcd('y/Two.VCD'), make_vcd('z/Three.VCD')
    window.add_paths([a, b])
    window.add_paths([a, Path(str(a).upper())])
    assert window.table.rowCount() == 2
    window.table.item(0, 1).setText('Edited title')
    window.add_paths([c])
    assert window.table.item(0, 1).text() == 'Edited title'
    window.table.selectRow(1)
    window.remove()
    assert [g.source for g in window.games()] == [a, c]


def test_problem_sources_marked_in_status(window, tmp_path):
    iso = tmp_path / 'g.iso'; iso.write_bytes(bytes(2048 * 4))
    window.add_paths([iso])
    bar = window.table.cellWidget(0, 4)
    assert bar.format() == PT['failed'] and '2048' in bar.toolTip()


def test_preview_tree_shows_final_structure(window, make_vcd, usb):
    window.add_paths([make_vcd("Tony Hawk's Pro Skater 2 (USA).VCD")])
    window.root_edit.setText(str(usb))
    top = top_items(window.tree)
    assert set(top) == {'APPS', 'POPS'}          # POPSTARTER folder copy is off by default
    assert top['APPS'].child(0).text(0) == 'XX.Tony_Hawks_Pro_Skater_2'
    assert top['APPS'].child(0).child(0).text(1) == PT['state_new']
    assert '1 jogo' in window.summary.text()


def test_embedded_resources_used_without_selection(window, resources_dir):
    summary = window.resources_status.text()
    assert summary.count(PT['origin_bundled']) == 2 and PT['origin_off'] in summary
    assert window.res.elf() == resources_dir / 'POPS' / 'POPSTARTER.ELF'
    names = sorted(rel.name for _, rel in window.res.shared())
    assert names == ['CHEATS.TXT', 'POPSTARTER.ELF', 'POPS_IOX.PAK']         # no .exe by default


def test_custom_files_override_and_persist(window, settings, tmp_path):
    mine = tmp_path / 'v2' / 'POPSTARTER.ELF'; mine.parent.mkdir(); mine.write_bytes(FAKE_ELF)
    dialog = gui.ResourcesDialog(window)
    dialog.edits['elf'].setText(str(mine))
    dialog.checks['include_windows'].setChecked(True)
    dialog.checks['copy_support'].setChecked(True)
    dialog.accept()
    window.refresh_resources()
    assert window.res.elf() == mine
    names = sorted(rel.as_posix() for _, rel in window.res.shared())
    assert 'POPS/PS1_USB_Converter.exe' in names and 'POPSTARTER/usbd.irx' in names
    again = gui.Window(settings)
    assert again.res.elf() == mine and again.res.flag('include_windows', False)
    again.close()


def test_missing_elf_is_reported(window, resources_dir, usb, make_vcd, monkeypatch):
    (resources_dir / 'POPS' / 'POPSTARTER.ELF').unlink()
    window.refresh_resources()
    assert PT['origin_missing'] in window.resources_status.text()
    errors = []
    monkeypatch.setattr(gui.QMessageBox, 'critical', lambda *a: errors.append(a[2]))
    window.add_paths([make_vcd('Game.VCD')]); window.root_edit.setText(str(usb))
    window.prepare()
    assert errors == [PT['elf_missing']] and list(usb.iterdir()) == []


def test_prepare_converts_copies_and_reports(window, app, usb, tmp_path, make_vcd, monkeypatch):
    lib = tmp_path / 'lib'; lib.mkdir()
    (lib / 'Crash.bin').write_bytes(data_sectors(20))
    cue = write_cue(lib, 'Crash', 'FILE "Crash.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00')
    window.add_paths([cue, make_vcd("Tony Hawk's Pro Skater 2 (USA).VCD")])
    window.root_edit.setText(str(usb))
    messages = run_install(window, app, monkeypatch)
    assert messages and messages[-1][0] == 'info', messages
    assert files_under(usb) == [
        'APPS/XX.Crash/XX.Crash.ELF', 'APPS/XX.Crash/title.cfg',
        'APPS/XX.Tony_Hawks_Pro_Skater_2/XX.Tony_Hawks_Pro_Skater_2.ELF', 'APPS/XX.Tony_Hawks_Pro_Skater_2/title.cfg',
        'POPS/CHEATS.TXT', 'POPS/Crash.VCD', 'POPS/Crash/SLOT0.VMC', 'POPS/Crash/SLOT1.VMC',
        'POPS/POPSTARTER.ELF', 'POPS/POPS_IOX.PAK',
        'POPS/Tony_Hawks_Pro_Skater_2.VCD', 'POPS/Tony_Hawks_Pro_Skater_2/SLOT0.VMC', 'POPS/Tony_Hawks_Pro_Skater_2/SLOT1.VMC']
    assert [window.table.cellWidget(r, 4).format() for r in range(2)] == [PT['ok'], PT['ok']]


def test_options_disable_vmc(window, app, usb, make_vcd, monkeypatch):
    window.vmc_box.setChecked(False)
    window.add_paths([make_vcd('Game.VCD')]); window.root_edit.setText(str(usb))
    run_install(window, app, monkeypatch)
    assert (usb / 'POPS' / 'Game.VCD').exists() and not (usb / 'POPS' / 'Game').exists()


def test_tools_create_vmcs_and_check_device(window, usb, monkeypatch):
    (usb / 'POPS').mkdir(); (usb / 'POPS' / 'Crash.VCD').write_bytes(b'X')
    window.root_edit.setText(str(usb))
    monkeypatch.setattr(gui.QMessageBox, 'question', lambda *a: gui.QMessageBox.StandardButton.Yes)
    infos = []
    monkeypatch.setattr(gui.QMessageBox, 'information', lambda *a: infos.append(a[2]))
    window.create_device_vmcs()
    assert (usb / 'POPS' / 'Crash' / 'SLOT0.VMC').exists() and infos[-1] == PT['vmc_done'].format(n=2)
    window.create_device_vmcs()
    assert infos[-1] == PT['vmc_none']
    html = window.device_report(usb)
    assert PT['dev_fs'] in html and PT['dev_vcds'] in html


def test_about_lists_credits():
    from pops_manager import credits
    text = credits.html('pt')
    for name in ('krHACKen', 'Eliminator14', 'El_Isra', 'CUE2POPS', 'VMC and MultiDisc Creator', 'PSXVCD', 'BDMAssault', 'Hugopocked'):
        assert name in text


def test_problem_files_skipped_and_finished_games_leave_preview(window, app, usb, tmp_path, make_vcd, monkeypatch):
    iso = tmp_path / 'bad.iso'; iso.write_bytes(bytes(2048 * 4))
    window.add_paths([iso, make_vcd('Good.VCD')]); window.root_edit.setText(str(usb))
    assert PT['skipped'].format(n=1) in window.summary.text()
    messages = run_install(window, app, monkeypatch)
    assert messages[-1] == ('info', PT['done_summary'].format(ok=1))
    assert (usb / 'POPS' / 'Good.VCD').exists() and not (usb / 'POPS' / 'bad.VCD').exists()
    assert window.summary.text() == PT['all_done'] and window.tree.topLevelItemCount() == 0
    assert window.table.cellWidget(1, 4).format() == PT['ok']


@pytest.fixture
def window_with_pack(app, settings, tmp_path, monkeypatch, resources_dir):
    """resources_dir plus a small fix pack in bundled/POPS/POPSUtils."""
    from test_fixes import write
    utils = resources_dir / 'POPS' / 'POPSUtils'
    game_fixes = utils / 'Pack' / 'POPS Game Fixes'
    write(game_fixes / "Tony Hawk's Pro Skater 2 [All versions]" / 'CHEATS.TXT', b'$SAFEMODE')
    write(game_fixes / "Tony Hawk's Pro Skater 2 [All versions]" / 'TROJAN_0.BIN')
    write(game_fixes / 'Final Fantasy VII' / 'Final Fantasy VII (USA)' / '4-3' / 'TROJAN_0.BIN', b'4:3')
    write(game_fixes / 'Final Fantasy VII' / 'Final Fantasy VII (USA)' / 'CHEATS.TXT')
    write(utils / 'Pack' / 'POPS General Fixes' / 'GPU Dithering Off' / 'TROJAN_9.BIN')
    write(utils / 'Compatibility_Modes' / 'PATCH_1.BIN', b'compat1')
    w = gui.Window(settings)
    yield w
    w.close()


def test_fixes_applied_automatically_and_installed(window_with_pack, app, usb, make_vcd, monkeypatch):
    w = window_with_pack
    assert '2 jogos com correção' in w.resources_status.text()
    w.add_paths([make_vcd("Tony Hawk's Pro Skater 2 (USA).VCD"), make_vcd('Crash Bandicoot (USA).VCD')])
    assert w.table.item(0, gui.COL_FIXES).text() == PT['fixes_count'].format(n=2)
    assert w.table.item(1, gui.COL_FIXES).text() == '—'
    w.root_edit.setText(str(usb))
    run_install(w, app, monkeypatch)
    folder = usb / 'POPS' / 'Tony_Hawks_Pro_Skater_2'
    assert (folder / 'CHEATS.TXT').read_bytes() == b'$SAFEMODE' and (folder / 'TROJAN_0.BIN').exists()
    assert not (usb / 'POPS' / 'Crash_Bandicoot' / 'CHEATS.TXT').exists()


def test_fixes_dialog_variant_compat_general_and_restore(window_with_pack, make_vcd):
    w = window_with_pack
    w.add_paths([make_vcd('Final Fantasy VII (USA) (Disc 1).VCD')])
    dialog = gui.FixesDialog(w, 0)
    assert sorted(dialog.files) == ['CHEATS.TXT']
    assert dialog.combos['fixes_variant'].count() == 1          # the 4-3 variant
    dialog.add_choice(dialog.combos['fixes_variant'])
    dialog.add_choice(dialog.combos['fixes_compat'])
    dialog.add_choice(dialog.combos['fixes_general'])
    assert sorted(dialog.files) == ['CHEATS.TXT', 'PATCH_1.BIN', 'TROJAN_0.BIN', 'TROJAN_9.BIN']
    dialog.accept()
    assert sorted(n for _, n in w.entries[0].fixes) == ['CHEATS.TXT', 'PATCH_1.BIN', 'TROJAN_0.BIN', 'TROJAN_9.BIN']
    again = gui.FixesDialog(w, 0)
    again.restore(); again.accept()
    assert [n for _, n in w.entries[0].fixes] == ['CHEATS.TXT']


def test_fixes_dialog_reports_replacement(window_with_pack, make_vcd):
    w = window_with_pack
    w.add_paths([make_vcd("Tony Hawk's Pro Skater 2 (USA).VCD")])
    dialog = gui.FixesDialog(w, 0)
    dialog.put([(Path(dialog.files['TROJAN_0.BIN']), 'TROJAN_0.BIN')])
    assert 'TROJAN_0.BIN' in dialog.message.text()


def test_short_names_setting_renames_list(window, settings, make_vcd, monkeypatch):
    window.add_paths([make_vcd("Tony Hawk's Pro Skater 2 (USA).VCD")])
    assert window.entries[0].slug == 'Tony_Hawks_Pro_Skater_2'
    window.table.item(0, gui.COL_TITLE).setText('Meu título')

    class TurnOnShortNames:                     # stands in for the settings dialog
        def __init__(self, _window):
            pass

        def exec(self):
            settings.setValue('short_names', 'true')
            return True
    monkeypatch.setattr(gui, 'ResourcesDialog', TurnOnShortNames)
    window.configure_resources()
    assert window.entries[0].slug == 'Tony_Hawks_Pro_Skate_2' and window.entries[0].title == 'Meu título'
    assert '22' in window.table.horizontalHeaderItem(gui.COL_SLUG).text()


def test_speed_and_slow_device_note(window):
    class Timer:
        def isValid(self): return True
        def elapsed(self): return 20_000         # ms
    window.overall.setRange(0, 3); window.overall.setValue(1)
    window.copy_total = 300 * 2**20
    window.copy_done = {0: 100 * 2**20, 1: 20 * 2**20}    # 120 MB in 20 s = 6 MB/s, 180 MB left = 30 s
    window.copy_timer = Timer()
    window.show_speed()
    assert window.overall.format() == PT['working_speed'].format(done=1, total=3, speed='6.0 MB', eta=PT['eta_less'])
    assert not window.speed_note.isHidden()
    assert window.speed_note.text() == PT['slow_device'].format(speed='6.0 MB')


def test_fast_device_has_no_note(window):
    class Timer:
        def isValid(self): return True
        def elapsed(self): return 20_000
    window.overall.setRange(0, 2); window.overall.setValue(0)
    window.copy_total = 4000 * 2**20
    window.copy_done = {0: 600 * 2**20}                   # 30 MB/s, 3400 MB left = ~2 min
    window.copy_timer = Timer()
    window.show_speed()
    assert window.overall.format() == PT['working_speed'].format(done=0, total=2, speed='30.0 MB', eta=PT['eta_min'].format(m=2))
    assert window.speed_note.isHidden()
