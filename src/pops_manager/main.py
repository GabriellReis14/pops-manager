"""PySide6 interface. Business rules live in core/convert/vmc/diagnostics; texts in i18n."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import os
import shutil
import sys
from PySide6.QtCore import QElapsedTimer, QLibraryInfo, QObject, QSettings, QThread, QTranslator, QUrl, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QFileDialog, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QCheckBox, QDialog,
    QDialogButtonBox, QMessageBox, QComboBox, QHeaderView, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QSplitter, QGroupBox, QTextBrowser, QAbstractItemView, QListWidget)
from pops_manager import convert, credits, diagnostics, fixes
from pops_manager.core import (Cancelled, Game, InstallResult, MAX_ID_LENGTH, SHORT_ID_LENGTH, Options, Progress,
    POPS_DIR, PAK_NAME, make_games, preview_items, install, plan_vmcs, create_vmcs, validate)
from pops_manager.i18n import LANGUAGES, QT_LOCALES, T
from pops_manager.resources import (ELF_REL, POPS_REL, SUPPORT_REL, UTILS_REL, Located, fix_folders, locate,
    pops_files, support_files)

STYLE_DONE = 'QProgressBar { color: #1b5e20; text-align: center; } QProgressBar::chunk { background: #a5d6a7; }'
STYLE_ERROR = 'QProgressBar { color: #c62828; text-align: center; }'
COL_FILE, COL_TITLE, COL_SLUG, COL_FIXES, COL_STATUS = range(5)
SLOW_DEVICE = 10 * 2**20          # bytes/s; below this the user is told the device is the bottleneck
STATE_COLORS = {'new': '#2e7d32', 'kept': '#757575', 'same': '#757575', 'different': '#ef6c00', 'exists': '#c62828'}


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return str(n)


def expand_drop(paths: list[Path]) -> list[Path]:
    """Files with a supported extension; folders are searched recursively."""
    found = []
    for path in paths:
        candidates = sorted(path.rglob('*')) if path.is_dir() else [path]
        found += [p for p in candidates if p.is_file() and p.suffix.lower() in convert.SUPPORTED]
    return convert.collapse_sources(found)


class Resources:
    """POPStarter files in use: user settings first, then the default locations."""
    ITEMS = {'elf': (ELF_REL, False), 'pops': (POPS_REL, True), 'support': (SUPPORT_REL, True), 'fixes': (UTILS_REL, True)}
    # checkbox settings and their defaults (POPSTARTER folder: opt-in, it belongs on the memory card)
    FLAGS = {'copy_pops': True, 'include_windows': False, 'copy_support': False, 'copy_fixes': True, 'short_names': False}

    def __init__(self, settings: QSettings):
        self.settings = settings
        self._pack: tuple[Path | None, fixes.FixPack | None] = (None, None)

    def custom(self, key: str) -> Path | None:
        value = str(self.settings.value(key, '') or '').strip()
        return Path(value) if value else None

    def flag(self, key: str, default: bool = True) -> bool:
        return str(self.settings.value(key, 'true' if default else 'false')).lower() == 'true'

    def enabled(self, key: str) -> bool:
        # POPStarter r13 loads usbd/usbhdfsd.irx from the memory card (mc0:/POPSTARTER/), not from USB,
        # so copying that folder to the device is opt-in.
        return key == 'elf' or self.flag(f'copy_{key}', self.FLAGS.get(f'copy_{key}', True))

    def default(self, key: str) -> Located:
        rel, folder = self.ITEMS[key]
        return locate(rel, folder=folder)

    def get(self, key: str) -> Located:
        rel, folder = self.ITEMS[key]
        return locate(rel, self.custom(key), folder=folder)

    def elf(self) -> Path | None:
        return self.get('elf').path

    def shared(self) -> list[tuple[Path, Path]]:
        files = []
        if self.enabled('pops'):
            files += pops_files(self.get('pops').path, self.flag('include_windows', False))
        if self.enabled('support'):
            files += support_files(self.get('support').path)
        return files

    def options(self) -> Options:
        return Options(vmc=self.flag('vmc'), multidisc=self.flag('multidisc'))

    def id_limit(self) -> int:
        return SHORT_ID_LENGTH if self.flag('short_names', False) else MAX_ID_LENGTH

    def fix_folders(self):
        return fix_folders(self.get('fixes').path)

    def fix_pack(self) -> fixes.FixPack | None:
        """Index of "POPS Game Fixes" (cached until the folder setting changes)."""
        folder = self.fix_folders().game_fixes
        if self._pack[0] != folder:
            self._pack = (folder, fixes.FixPack(folder) if folder else None)
        return self._pack[1]


class ResourcesDialog(QDialog):
    def __init__(self, window: Window):
        super().__init__(window)
        self.window_ = window
        tr, res = window.tr_, window.res
        self.setWindowTitle(tr('resources_title')); self.setMinimumWidth(760)
        grid = QGridLayout(self)
        self.edits: dict[str, QLineEdit] = {}
        for row, key in enumerate(Resources.ITEMS):
            edit = QLineEdit(str(res.custom(key) or ''))
            edit.setPlaceholderText(tr('default_hint').format(path=res.default(key).path or tr('origin_missing')))
            browse = QPushButton('...'); browse.clicked.connect(lambda _=False, k=key: self.browse(k))
            reset = QPushButton(tr('default')); reset.clicked.connect(edit.clear)
            grid.addWidget(QLabel(tr(key)), row, 0); grid.addWidget(edit, row, 1)
            grid.addWidget(browse, row, 2); grid.addWidget(reset, row, 3)
            self.edits[key] = edit
        self.checks = {}
        row = len(Resources.ITEMS)
        for row, (key, default) in enumerate(Resources.FLAGS.items(), start=row):
            box = QCheckBox(tr(key)); box.setChecked(res.flag(key, default))
            grid.addWidget(box, row, 0, 1, 4); self.checks[key] = box
        note = QLabel(tr('keep_note')); note.setWordWrap(True)
        grid.addWidget(note, row + 1, 0, 1, 4)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, row + 2, 0, 1, 4)

    def browse(self, key: str):
        tr = self.window_.tr_
        if key == 'elf':
            value, _ = QFileDialog.getOpenFileName(self, tr(key), '', 'POPSTARTER.ELF (*.ELF *.elf)')
        else:
            value = QFileDialog.getExistingDirectory(self, tr(key))
        if value: self.edits[key].setText(value)

    def accept(self):
        settings = self.window_.settings
        for key, edit in self.edits.items():
            settings.setValue(key, edit.text().strip())
        for key, box in self.checks.items():
            settings.setValue(key, 'true' if box.isChecked() else 'false')
        settings.sync()
        super().accept()


class FixesDialog(QDialog):
    """Shows the fixes of one game and lets the user add variants, compatibility modes, general fixes
    or their own files. The result is Game.fixes: files copied to POPS/<ID>/."""

    def __init__(self, window: Window, row: int):
        super().__init__(window)
        self.window_, self.row = window, row
        tr = window.tr_
        game = window.entries[row]
        self.match = window.matches.get(_path_key(game.source))
        self.files: dict[str, Path] = {name: source for source, name in game.fixes}
        folders = window.res.fix_folders()
        self.roots = [r for r in (folders.game_fixes, folders.general_fixes, folders.compatibility) if r]
        self.setWindowTitle(tr('fixes_title').format(game=game.title)); self.resize(760, 560)
        layout = QVBoxLayout(self)
        info = QLabel(tr('fixes_found').format(label=self.match.label) if self.match else tr('fixes_none'))
        info.setWordWrap(True); layout.addWidget(info)
        if self.match and self.match.version_unknown:
            warn = QLabel('⚠ ' + tr('fixes_version_unknown')); warn.setWordWrap(True); layout.addWidget(warn)
        if self.match and self.match.image_patches:
            row_ = QHBoxLayout(); layout.addLayout(row_)
            patch = QLabel('⚠ ' + tr('fixes_image_patches')); patch.setWordWrap(True); row_.addWidget(patch, 1)
            folder = self.match.image_patches[0].parent
            button = QPushButton(tr('open_folder')); button.clicked.connect(lambda: self.open(folder)); row_.addWidget(button)
        if self.match and self.match.notes:
            row_ = QHBoxLayout(); layout.addLayout(row_); row_.addWidget(QLabel(tr('fixes_notes')))
            for note in self.match.notes:
                button = QPushButton(note.name); button.clicked.connect(lambda _=False, n=note: self.open(n)); row_.addWidget(button)
            row_.addStretch()
        layout.addWidget(QLabel(tr('fixes_list').format(slug=game.slug)))
        self.list = QListWidget(); layout.addWidget(self.list, 1)
        self.message = QLabel(); self.message.setStyleSheet('color: #ef6c00'); layout.addWidget(self.message)
        grid = QGridLayout(); layout.addLayout(grid)
        base = self.match.game_folder if self.match else None
        variants = [(str(v.relative_to(base)), v) for v in (self.match.variants if self.match else [])]
        general_root = folders.general_fixes
        general = [(str(g.relative_to(general_root)), g) for g in fixes.general_fixes(general_root)]
        modes = [(f.stem, f) for f in fixes.compatibility_modes(folders.compatibility)]
        self.combos = {}
        for r, (key, options, tip) in enumerate([('fixes_variant', variants, ''), ('fixes_compat', modes, tr('fixes_compat_tip')),
                                                 ('fixes_general', general, '')]):
            combo = QComboBox(); combo.setToolTip(tip)
            for label, path in options:
                combo.addItem(label, str(path))
            add = QPushButton(tr('fixes_add')); add.clicked.connect(lambda _=False, c=combo: self.add_choice(c))
            combo.setEnabled(bool(options)); add.setEnabled(bool(options))
            grid.addWidget(QLabel(tr(key)), r, 0); grid.addWidget(combo, r, 1); grid.addWidget(add, r, 2)
            self.combos[key] = combo
        grid.setColumnStretch(1, 1)
        buttons_row = QHBoxLayout(); layout.addLayout(buttons_row)
        for key, slot in (('fixes_files', self.add_files), ('fixes_remove', self.remove_selected), ('fixes_auto', self.restore)):
            button = QPushButton(tr(key)); button.clicked.connect(slot); buttons_row.addWidget(button)
        buttons_row.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); layout.addWidget(box)
        self.refresh()

    @staticmethod
    def open(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def refresh(self) -> None:
        self.list.clear()
        for name, source in sorted(self.files.items()):
            shown = next((str(source.relative_to(r)) for r in self.roots if source.is_relative_to(r)), str(source))
            self.list.addItem(f'{name}    \u2190  {shown}')
            self.list.item(self.list.count() - 1).setToolTip(str(source))

    def put(self, items: list[tuple[Path, str]]) -> None:
        replaced = [name for _, name in items if name in self.files]
        for source, name in items:
            self.files[name] = source
        self.message.setText(' '.join(self.window_.tr_('fixes_replaced').format(name=n) for n in replaced))
        self.refresh()

    def add_choice(self, combo: QComboBox) -> None:
        path = Path(combo.currentData())
        self.put([(path, path.name.upper())] if path.is_file() else fixes.folder_files(path))

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self.window_.tr_('fixes_files'), '', self.window_.tr_('fixes_files_filter'))
        self.put([(Path(p), Path(p).name.upper()) for p in paths])

    def remove_selected(self) -> None:
        names = sorted(self.files)
        for index in sorted((self.list.row(i) for i in self.list.selectedItems()), reverse=True):
            self.files.pop(names[index], None)
        self.message.clear(); self.refresh()

    def restore(self) -> None:
        self.files = {name: source for source, name in (self.match.files if self.match else [])}
        self.message.clear(); self.refresh()

    def accept(self) -> None:
        game = self.window_.entries[self.row]
        self.window_.entries[self.row] = replace(game, fixes=tuple((src, name) for name, src in sorted(self.files.items())))
        super().accept()


class InstallWorker(QObject):
    """Runs core.install in a background thread and reports progress through signals."""
    progress = Signal(object)          # core.Progress
    finished = Signal(object, object)  # InstallResult, {vcd name: fragments}
    failed = Signal(str)

    def __init__(self, root: Path, games: list[Game], elf: Path, shared, options: Options):
        super().__init__()
        self.args = (root, games, elf, shared, options)
        self.cancel_requested = False
        self._last: dict[tuple, int] = {}

    def on_progress(self, event: Progress) -> None:
        if self.cancel_requested:
            raise Cancelled()
        percent = int(event.done * 100 / event.total) if event.total else 0
        key = (event.game, event.step)
        if event.step in ('convert', 'copy') and self._last.get(key) == percent:
            return                             # throttle: one signal per percent
        self._last[key] = percent
        self.progress.emit(event)

    def run(self):
        try:
            root, games, elf, shared, options = self.args
            result = install(root, games, elf, shared, options, self.on_progress)
            fragmented = {}
            for path in result.vcds.values():
                try:
                    count = diagnostics.fragments(path)
                except OSError:
                    continue
                if count > 1:
                    fragmented[path.name] = count
            self.finished.emit(result, fragmented)
        except Exception as error:
            self.failed.emit(str(error))


class Window(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings('POPS Manager', 'POPS Manager')
        self.res = Resources(self.settings)
        self.language = 'pt'
        self.entries: list[Game] = []
        self.problems: dict[str, str] = {}            # source key -> conversion problem
        self.sizes: dict[str, int] = {}
        self.completed: set[str] = set()              # sources installed in this session
        self.run_rows: list[int] = []                 # table row of each game being installed
        self.matches: dict[str, fixes.FixMatch | None] = {}   # source key -> fix pack match
        self.copy_done: dict[int, int] = {}           # game index -> bytes written to the device
        self.copy_total = 0
        self.copy_timer = QElapsedTimer()
        self.thread: QThread | None = None
        self.worker: InstallWorker | None = None
        self.qt_translator = QTranslator(self)
        self.setMinimumSize(980, 680)
        self.setAcceptDrops(True)

        menu = self.menuBar()
        self.settings_menu = menu.addMenu(''); self.tools_menu = menu.addMenu(''); self.help_menu = menu.addMenu('')
        self.resources_action = self.settings_menu.addAction(''); self.resources_action.triggered.connect(self.configure_resources)
        self.check_action = self.tools_menu.addAction(''); self.check_action.triggered.connect(self.check_device)
        self.vmc_action = self.tools_menu.addAction(''); self.vmc_action.triggered.connect(self.create_device_vmcs)
        self.about_action = self.help_menu.addAction(''); self.about_action.triggered.connect(self.about)

        body = QWidget(); self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        top = QHBoxLayout(); layout.addLayout(top)
        self.add_button = QPushButton(); self.add_button.clicked.connect(self.add)
        self.remove_button = QPushButton(); self.remove_button.clicked.connect(self.remove)
        self.fixes_button = QPushButton(); self.fixes_button.clicked.connect(self.edit_fixes)
        self.language_box = QComboBox(); self.language_box.addItems(list(LANGUAGES.values()))
        saved = str(self.settings.value('language', 'pt'))
        if saved in LANGUAGES: self.language_box.setCurrentIndex(list(LANGUAGES).index(saved))
        self.language_box.currentIndexChanged.connect(self.translate)
        top.addWidget(self.add_button); top.addWidget(self.remove_button); top.addWidget(self.fixes_button); top.addStretch()
        top.addWidget(QLabel('Language / Idioma:')); top.addWidget(self.language_box)

        splitter = QSplitter(Qt.Orientation.Vertical); layout.addWidget(splitter, 1)
        self.table = QTableWidget(0, 5)
        header = self.table.horizontalHeader()
        for col, mode in enumerate([QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.Fixed]):
            header.setSectionResizeMode(col, mode)
        self.table.setColumnWidth(COL_STATUS, 190)
        self.table.cellDoubleClicked.connect(lambda row, col: self.edit_fixes(row) if col == COL_FIXES else None)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self.sync_entries)
        self.drop_label = QLabel(); self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet('color: gray; padding: 6px;')
        table_box = QWidget(); tl = QVBoxLayout(table_box); tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.table); tl.addWidget(self.drop_label)
        splitter.addWidget(table_box)
        self.preview_box = QGroupBox(); pl = QVBoxLayout(self.preview_box)
        self.tree = QTreeWidget(); self.tree.setColumnCount(2)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.summary = QLabel(); self.summary.setWordWrap(True)
        pl.addWidget(self.tree); pl.addWidget(self.summary)
        splitter.addWidget(self.preview_box)
        splitter.setSizes([330, 260])

        grid = QGridLayout(); layout.addLayout(grid)
        self.root_label = QLabel()
        self.root_edit = QLineEdit(str(self.settings.value('root', '') or ''))
        self.root_edit.textChanged.connect(self.refresh_preview)
        browse = QPushButton('...'); browse.clicked.connect(self.pick_root)
        grid.addWidget(self.root_label, 0, 0); grid.addWidget(self.root_edit, 0, 1); grid.addWidget(browse, 0, 2)
        self.resources_label = QLabel()
        self.resources_status = QLabel(); self.resources_status.setWordWrap(True)
        self.configure_button = QPushButton(); self.configure_button.clicked.connect(self.configure_resources)
        grid.addWidget(self.resources_label, 1, 0); grid.addWidget(self.resources_status, 1, 1); grid.addWidget(self.configure_button, 1, 2)
        options = QHBoxLayout(); grid.addLayout(options, 2, 1)
        self.vmc_box = QCheckBox(); self.vmc_box.setChecked(self.res.flag('vmc'))
        self.multidisc_box = QCheckBox(); self.multidisc_box.setChecked(self.res.flag('multidisc'))
        for box, key in ((self.vmc_box, 'vmc'), (self.multidisc_box, 'multidisc')):
            box.toggled.connect(lambda checked, k=key: (self.settings.setValue(k, 'true' if checked else 'false'), self.refresh_preview()))
            options.addWidget(box)
        options.addStretch()
        grid.setColumnStretch(1, 1)

        self.speed_note = QLabel(); self.speed_note.setWordWrap(True); self.speed_note.setVisible(False)
        self.speed_note.setStyleSheet('color: #ef6c00')
        layout.addWidget(self.speed_note)
        bottom = QHBoxLayout(); layout.addLayout(bottom)
        self.overall = QProgressBar(); self.overall.setVisible(False)
        self.install_button = QPushButton(); self.install_button.setMinimumHeight(36)
        self.install_button.clicked.connect(self.prepare)
        self.cancel_button = QPushButton(); self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel)
        bottom.addWidget(self.overall, 1); bottom.addStretch(); bottom.addWidget(self.cancel_button); bottom.addWidget(self.install_button)
        self.translate()

    # --- texts ---------------------------------------------------------------------------------
    def tr_(self, key: str) -> str:
        return T[self.language][key]

    def translate(self):
        self.language = list(LANGUAGES)[self.language_box.currentIndex()]
        self.settings.setValue('language', self.language)
        QApplication.removeTranslator(self.qt_translator)
        # Standard Qt buttons (Yes/No/Cancel); no file is needed for English.
        if self.qt_translator.load(f'qtbase_{QT_LOCALES[self.language]}', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            QApplication.installTranslator(self.qt_translator)
        tr = self.tr_
        self.setWindowTitle(tr('window'))
        self.settings_menu.setTitle(tr('settings_menu')); self.tools_menu.setTitle(tr('tools_menu')); self.help_menu.setTitle(tr('help_menu'))
        self.resources_action.setText(tr('resources_title') + '...'); self.check_action.setText(tr('check_device'))
        self.vmc_action.setText(tr('create_vmcs')); self.about_action.setText(tr('about'))
        self.add_button.setText(tr('add')); self.remove_button.setText(tr('remove')); self.fixes_button.setText(tr('fixes_button'))
        self.table.setHorizontalHeaderLabels([tr('game'), tr('title'), tr('slug').format(n=self.res.id_limit()),
                                              tr('fixes_col'), tr('status')])
        self.drop_label.setText(tr('drop_hint'))
        self.preview_box.setTitle(tr('preview_title')); self.tree.setHeaderLabels([tr('col_item'), tr('col_state')])
        self.root_label.setText(tr('root')); self.resources_label.setText(tr('popstarter')); self.configure_button.setText(tr('configure'))
        self.vmc_box.setText(tr('opt_vmc')); self.vmc_box.setToolTip(tr('opt_vmc_tip'))
        self.multidisc_box.setText(tr('opt_multidisc')); self.multidisc_box.setToolTip(tr('opt_multidisc_tip'))
        self.install_button.setText(tr('prepare')); self.cancel_button.setText(tr('cancel'))
        self.populate()
        self.refresh_resources()

    # --- resources -----------------------------------------------------------------------------
    def resource_summary(self) -> str:
        parts = []
        for key in Resources.ITEMS:
            found = self.res.get(key)
            if not self.res.enabled(key):
                state = '— ' + self.tr_('origin_off')
            elif found.path is None or (key == 'elf' and not found.path.is_file()) or (key != 'elf' and not found.path.is_dir()):
                state = '✖ ' + self.tr_('origin_missing')
            else:
                state = '✔ ' + self.tr_(f'origin_{found.origin}')
                if key == 'pops':
                    state += ', ' + self.tr_('files').format(n=len(pops_files(found.path, self.res.flag('include_windows', False))))
                if key == 'support':
                    state += ', ' + self.tr_('files').format(n=len(support_files(found.path)))
                if key == 'fixes':
                    pack = self.res.fix_pack()
                    state += ', ' + self.tr_('fixes_games').format(n=len(pack) if pack else 0)
            parts.append(f'{self.tr_(key)}: {state}')
        return '  ·  '.join(parts)

    def refresh_resources(self):
        self.resources_status.setText(self.resource_summary())
        self.refresh_preview()

    def configure_resources(self):
        limit = self.res.id_limit()
        if ResourcesDialog(self).exec():
            if self.res.id_limit() != limit:          # naming mode changed: new identifiers, titles/fixes kept
                renamed = make_games([g.source for g in self.entries], limit=self.res.id_limit())
                self.entries = [replace(g, slug=r.slug) for g, r in zip(self.entries, renamed)]
                self.table.setHorizontalHeaderItem(COL_SLUG, QTableWidgetItem(self.tr_('slug').format(n=self.res.id_limit())))
                self.populate()
            self.refresh_resources()

    # --- game list -----------------------------------------------------------------------------
    def add_paths(self, paths: list[Path]) -> None:
        known = {_path_key(g.source) for g in self.entries}
        new = []
        for path in convert.collapse_sources(paths):
            if _path_key(path) not in known:
                known.add(_path_key(path)); new.append(path)
        for path in new:
            try:
                self.sizes[_path_key(path)] = convert.probe(path)
            except (OSError, ValueError) as error:
                self.problems[_path_key(path)] = str(error)
        games = make_games(new, taken={g.slug for g in self.entries}, limit=self.res.id_limit())
        pack = self.res.fix_pack() if self.res.enabled('fixes') else None
        for i, game in enumerate(games):
            match = pack.match(game.source.stem) if pack else None
            self.matches[_path_key(game.source)] = match
            if match and match.files:
                games[i] = replace(game, fixes=tuple(match.files))
        self.entries += games
        self.populate()

    def edit_fixes(self, row: int | None = None) -> None:
        if row is None or isinstance(row, bool):
            row = self.table.currentRow()
        if row < 0 or row >= len(self.entries) or self.busy():
            return
        if FixesDialog(self, row).exec():
            self.populate()

    def fixes_label(self, game: Game) -> tuple[str, str]:
        """Text and tooltip of the fixes column."""
        match = self.matches.get(_path_key(game.source))
        tip = '\n'.join([match.label] if match else []) + ''.join(f'\n{name}' for _, name in game.fixes)
        if game.fixes:
            return self.tr_('fixes_count').format(n=len(game.fixes)), tip.strip()
        if match and match.version_unknown:
            return self.tr_('fixes_pick'), tip.strip()
        if match and match.image_patches:
            return self.tr_('fixes_patch_only'), tip.strip()
        return '—', ''

    def add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr_('add'), '', self.tr_('add_filter'))
        self.add_paths([Path(p) for p in paths])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths(expand_drop([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]))

    def remove(self):
        rows = {x.row() for x in self.table.selectedItems()}
        self.entries = [g for i, g in enumerate(self.entries) if i not in rows]
        self.populate()

    def status_bar(self, row: int) -> QProgressBar:
        bar = self.table.cellWidget(row, COL_STATUS)
        if not isinstance(bar, QProgressBar):
            bar = QProgressBar(); bar.setRange(0, 100); bar.setTextVisible(True)
            self.table.setCellWidget(row, COL_STATUS, bar)
        return bar

    def set_status(self, row: int, text: str, percent: int = 0, style: str = '', tip: str = '') -> None:
        bar = self.status_bar(row)
        bar.setValue(percent); bar.setFormat(text); bar.setToolTip(tip); bar.setStyleSheet(style)

    def populate(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.entries))
        for row, game in enumerate(self.entries):
            item = QTableWidgetItem(game.source.name); item.setToolTip(str(game.source))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, COL_TITLE, QTableWidgetItem(game.title))
            self.table.setItem(row, COL_SLUG, QTableWidgetItem(game.slug))
            text, tip = self.fixes_label(game)
            fix_item = QTableWidgetItem(text); fix_item.setToolTip(tip)
            fix_item.setFlags(fix_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, COL_FIXES, fix_item)
            problem = self.problems.get(_path_key(game.source))
            if problem:
                self.set_status(row, self.tr_('failed'), 0, STYLE_ERROR, problem)
            elif _path_key(game.source) in self.completed:
                self.set_status(row, self.tr_('ok'), 100, STYLE_DONE)
            else:
                self.set_status(row, self.tr_('ready'))
        self.table.blockSignals(False)
        self.drop_label.setVisible(not self.entries)
        self.refresh_preview()

    def sync_entries(self):
        """Keeps user edits so they survive adding or removing other games."""
        for row, game in enumerate(self.entries):
            title, slug = self.table.item(row, COL_TITLE), self.table.item(row, COL_SLUG)
            if title and slug:
                self.entries[row] = replace(game, title=title.text().strip(), slug=slug.text().strip())
        self.refresh_preview()

    def pick_root(self):
        value = QFileDialog.getExistingDirectory(self, self.tr_('root'), self.root_edit.text())
        if value: self.root_edit.setText(value)

    def games(self) -> list[Game]:
        for row, game in enumerate(self.entries, start=1):
            if not game.title or not game.slug:
                raise ValueError(self.tr_('invalid_row').format(row=row))
        return list(self.entries)

    def pending(self) -> tuple[list[int], list[Game]]:
        """Rows still to install: not finished in this session and without a conversion problem."""
        rows = [i for i, g in enumerate(self.games()) if _path_key(g.source) not in self.completed
                and _path_key(g.source) not in self.problems]
        return rows, [self.entries[i] for i in rows]

    def skipped(self) -> int:
        return sum(1 for g in self.entries if _path_key(g.source) in self.problems)

    def root(self) -> Path | None:
        text = self.root_edit.text().strip()
        return Path(text) if text else None

    # --- preview -------------------------------------------------------------------------------
    def warnings(self, root: Path) -> list[str]:
        has_pak = any(rel.name.upper() == PAK_NAME for _, rel in self.res.shared())
        if not has_pak and not (root / POPS_DIR / PAK_NAME).exists():
            return [self.tr_('pak_missing')]
        return []

    def refresh_preview(self):
        if not hasattr(self, 'summary'): return
        self.tree.clear()
        root = self.root()
        if root is None or not root.is_dir():
            self.summary.setText(self.tr_('no_root')); return
        self.settings.setValue('root', str(root))
        if not self.entries:
            self.summary.setText(self.tr_('no_games')); return
        try:
            _, games = self.pending()
            if not games:
                self.summary.setText(self.tr_('all_done')); return
            items = preview_items(root, games, self.res.shared(), self.res.options())
        except Exception as error:
            self.summary.setText(str(error)); return
        nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
        for item in items:
            parts = item.rel.parts
            for depth in range(1, len(parts) + 1):
                key = parts[:depth]
                if key in nodes:
                    continue
                parent = nodes.get(parts[:depth - 1])
                node = QTreeWidgetItem([parts[depth - 1], ''])
                (parent.addChild(node) if parent else self.tree.addTopLevelItem(node))
                nodes[key] = node
            leaf = nodes[parts]
            leaf.setText(1, self.tr_(f'state_{item.state}'))
            leaf.setForeground(1, QBrush(QColor(STATE_COLORS[item.state])))
        self.tree.expandToDepth(1)
        total = sum(self.sizes.get(_path_key(g.source), 0) for g in games)
        free = shutil.disk_usage(root).free
        text = self.tr_('summary').format(games=len(games), size=human_size(total), free=human_size(free))
        notes = self.warnings(root) + ([self.tr_('skipped').format(n=self.skipped())] if self.skipped() else [])
        self.summary.setText('\n'.join([text] + ['⚠ ' + w for w in notes]))

    # --- installation --------------------------------------------------------------------------
    def busy(self) -> bool:
        return self.thread is not None

    def set_busy(self, busy: bool) -> None:
        for widget in (self.add_button, self.remove_button, self.fixes_button, self.install_button, self.root_edit,
                       self.configure_button, self.vmc_box, self.multidisc_box, self.menuBar()):
            widget.setEnabled(not busy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers if busy else
                                   QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.cancel_button.setVisible(busy); self.cancel_button.setEnabled(busy); self.overall.setVisible(busy)

    def prepare(self):
        try:
            rows, games = self.pending(); root = self.root()
            if root is None:
                raise ValueError(self.tr_('need_root'))
            elf = self.res.elf()
            if elf is None:
                raise ValueError(self.tr_('elf_missing'))
            if not games:
                raise ValueError(self.tr_('all_done') if self.entries else self.tr_('no_games'))
            shared, options = self.res.shared(), self.res.options()
            needed = validate(games, root, elf, shared, options)
        except Exception as error:
            QMessageBox.critical(self, self.tr_('error'), str(error)); return
        text = self.tr_('confirm').format(n=len(games), root=root, size=human_size(needed))
        warnings = self.warnings(root) + ([self.tr_('skipped').format(n=self.skipped())] if self.skipped() else [])
        text += '\n\n' + self.tr_('confirm_speed')
        if warnings:
            text += '\n\n⚠ ' + '\n⚠ '.join(warnings)
        if QMessageBox.question(self, self.tr_('prepare'), text) != QMessageBox.StandardButton.Yes:
            return
        self.run_rows = rows
        self.copy_done = {}
        self.copy_total = sum(self.sizes.get(_path_key(g.source), 0) for g in games)
        self.copy_timer.invalidate()
        self.speed_note.setVisible(False)
        for row in rows:
            self.set_status(row, self.tr_('queued'))
        self.overall.setRange(0, len(games)); self.overall.setValue(0)
        self.overall.setFormat(self.tr_('working').format(done=0, total=len(games)))
        self.set_busy(True)
        self.thread = QThread(self)
        self.worker = InstallWorker(root, games, elf, shared, options)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.thread.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel_requested = True
            self.cancel_button.setEnabled(False)

    def on_progress(self, event: Progress):
        if event.game is None:
            self.overall.setFormat(self.tr_('shared_copying').format(name=event.message)); return
        percent = int(event.done * 100 / event.total) if event.total else 0
        row = self.run_rows[event.game]
        if event.step == 'convert':
            self.set_status(row, self.tr_('converting').format(p=percent), percent)
        elif event.step == 'copy':
            self.set_status(row, self.tr_('copying').format(p=percent), percent)
            if not self.copy_timer.isValid():
                self.copy_timer.start()
            self.copy_done[event.game] = event.done
            self.show_speed()
        elif event.step == 'done':
            self.completed.add(_path_key(self.entries[row].source))
            self.set_status(row, self.tr_('ok'), 100, STYLE_DONE)
        elif event.step == 'error':
            self.set_status(row, self.tr_('failed'), 0, STYLE_ERROR, event.message)
        if event.step in ('done', 'error'):
            self.copy_done[event.game] = self.sizes.get(_path_key(self.entries[row].source), 0)
            self.overall.setValue(self.overall.value() + 1)
            self.show_speed()

    def show_speed(self) -> None:
        """Overall bar: games done, write speed and time left; warns when the device is slow."""
        done, total = self.overall.value(), self.overall.maximum()
        elapsed = self.copy_timer.elapsed() / 1000 if self.copy_timer.isValid() else 0
        written = sum(self.copy_done.values())
        if elapsed < 2 or written <= 0:
            self.overall.setFormat(self.tr_('working').format(done=done, total=total)); return
        speed = written / elapsed
        left = max(self.copy_total - written, 0) / speed
        eta = self.tr_('eta_less') if left < 60 else self.tr_('eta_min').format(m=round(left / 60))
        self.overall.setFormat(self.tr_('working_speed').format(done=done, total=total, speed=human_size(int(speed)), eta=eta))
        if elapsed > 15 and speed < SLOW_DEVICE and not self.speed_note.isVisible():
            self.speed_note.setText(self.tr_('slow_device').format(speed=human_size(int(speed))))
            self.speed_note.setVisible(True)

    def _stop_thread(self):
        if self.thread:
            self.thread.quit(); self.thread.wait()
        self.thread = self.worker = None
        self.set_busy(False)

    def on_finished(self, result: InstallResult, fragmented: dict[str, int]):
        self._stop_thread()
        lines = [self.tr_('done_summary').format(ok=len(result.done))]
        if result.failed:
            lines += ['', self.tr_('failed_summary').format(n=len(result.failed))]
            lines += [f'• {self.entries[self.run_rows[i]].source.name}: {msg}' for i, msg in result.failed.items()]
        if result.cancelled:
            lines += ['', self.tr_('cancelled')]
            for row in self.run_rows:
                if _path_key(self.entries[row].source) not in self.completed and self.status_bar(row).format() != self.tr_('failed'):
                    self.set_status(row, self.tr_('ready'))
        if fragmented:
            lines += ['', self.tr_('frag_warning')] + [f'• {self.tr_("dev_frag_item").format(name=n, n=c)}' for n, c in fragmented.items()]
        box = QMessageBox.warning if (result.failed or result.cancelled or fragmented) else QMessageBox.information
        box(self, self.tr_('prepare'), '\n'.join(lines))
        self.refresh_preview()

    def on_failed(self, message: str):
        self._stop_thread()
        QMessageBox.critical(self, self.tr_('error'), message)

    def closeEvent(self, event):
        if self.busy():
            event.ignore(); return
        super().closeEvent(event)

    # --- tools ---------------------------------------------------------------------------------
    def device_report(self, root: Path) -> str:
        tr = self.tr_
        info = diagnostics.device_info(root)
        rows = [(tr('dev_model'), info.model or '?'), (tr('dev_fs'), info.filesystem), (tr('dev_partition'), info.partition_style),
                (tr('dev_cluster'), human_size(info.cluster_size) if info.cluster_size else '?'),
                (tr('dev_sector'), f'{info.sector_size} B' if info.sector_size else '?'),
                (tr('dev_type'), info.drive_type),
                (tr('dev_space'), f'{human_size(info.free)} / {human_size(info.total)}'),
                (tr('dev_vcds'), str(info.vcd_count))]
        html = '<table>' + ''.join(f'<tr><td><b>{k}</b>&nbsp;&nbsp;</td><td>{v}</td></tr>' for k, v in rows) + '</table>'
        warnings = info.warnings()
        if warnings:
            html += '<ul>' + ''.join(f'<li style="color:#c62828">{tr("warn_" + w)}</li>' for w in warnings) + '</ul>'
            if info.fragmented:
                html += '<ul>' + ''.join(f'<li>{tr("dev_frag_item").format(name=n, n=c)}</li>' for n, c in info.fragmented.items()) + '</ul>'
        else:
            html += f'<p style="color:#2e7d32">{tr("dev_ok")}</p>'
        return html

    def check_device(self):
        root = self.root()
        if root is None or not root.is_dir():
            QMessageBox.information(self, self.tr_('device_title'), self.tr_('need_root')); return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            html = self.device_report(root)
        finally:
            QApplication.restoreOverrideCursor()
        box = QMessageBox(self); box.setWindowTitle(self.tr_('device_title'))
        box.setTextFormat(Qt.TextFormat.RichText); box.setText(html); box.exec()

    def create_device_vmcs(self):
        root = self.root()
        if root is None or not root.is_dir():
            QMessageBox.information(self, self.tr_('create_vmcs'), self.tr_('need_root')); return
        options = Options(vmc=True, multidisc=self.multidisc_box.isChecked())
        missing = plan_vmcs(root, options)
        if not missing:
            QMessageBox.information(self, self.tr_('create_vmcs'), self.tr_('vmc_none')); return
        question = self.tr_('vmc_confirm').format(n=len(missing), root=root)
        if QMessageBox.question(self, self.tr_('create_vmcs'), question) != QMessageBox.StandardButton.Yes:
            return
        try:
            created = create_vmcs(root, options)
        except Exception as error:
            QMessageBox.critical(self, self.tr_('error'), str(error)); return
        QMessageBox.information(self, self.tr_('create_vmcs'), self.tr_('vmc_done').format(n=len(created)))
        self.refresh_preview()

    def about(self):
        dialog = QDialog(self); dialog.setWindowTitle(self.tr_('about').rstrip('.'))
        dialog.resize(640, 520)
        layout = QVBoxLayout(dialog)
        text = QTextBrowser(); text.setOpenExternalLinks(True); text.setHtml(credits.html(self.language))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()


def smoke_test(window: Window, expect_bundled: bool = False, expect_fixes: bool = False) -> int:
    """Used by scripts/build_windows.ps1 to check a frozen build: window, translations, embedded files."""
    for index in range(len(LANGUAGES)):
        window.language_box.setCurrentIndex(index)
        if window.language != 'en' and window.qt_translator.isEmpty():
            return 1
    if expect_bundled and any(window.res.default(k).origin != 'bundled' for k in ('elf', 'pops', 'support')):
        return 2
    if expect_fixes and (window.res.default('fixes').origin != 'bundled' or not window.res.fix_pack()):
        return 4
    try:
        import py7zr  # noqa: F401  (imported lazily by convert; make sure the build includes it)
    except ImportError:
        return 3
    return 0


def main():
    app = QApplication(sys.argv)
    if '--smoke-test' in sys.argv:
        # isolated settings so a user's configuration cannot hide build problems
        settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, 'POPS Manager', 'smoke-test')
        settings.clear()
        window = Window(settings); window.show(); app.processEvents()
        sys.exit(smoke_test(window, '--expect-bundled' in sys.argv, '--expect-fixes' in sys.argv))
    window = Window(); window.show()
    sys.exit(app.exec())

if __name__ == '__main__': main()
