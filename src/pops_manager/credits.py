"""About / credits text. POPS Manager reimplements behaviour observed in these tools and documents;
it contains none of their code or binaries."""
from pops_manager import __version__

_INTRO = {
    'pt': 'Ferramenta livre (MIT) para preparar jogos de PS1 para POPStarter + OPL em pendrive/HD. '
          'Ela reproduz o comportamento das ferramentas abaixo, que vieram antes e tornaram isso possível. '
          'Nenhum código ou binário delas é distribuído junto.',
    'en': 'Free (MIT) tool to prepare PS1 games for POPStarter + OPL on USB drives. It reproduces the behaviour '
          'of the tools below, which came first and made this possible. None of their code or binaries is distributed.',
    'es': 'Herramienta libre (MIT) para preparar juegos de PS1 para POPStarter + OPL en USB/HD. Reproduce el '
          'comportamiento de las herramientas siguientes, que llegaron antes y lo hicieron posible. '
          'No se distribuye código ni binarios de ellas.',
}
_HEADINGS = {
    'pt': ('Créditos e agradecimentos', 'Bibliotecas'),
    'en': ('Credits and thanks', 'Libraries'),
    'es': ('Créditos y agradecimientos', 'Bibliotecas'),
}
# (name, author, what POPS Manager took from it)
CREDITS = [
    ('POPStarter', 'krHACKen (kHn)', 'PS1 launcher for the PS2; documentation by Shaolin Assassin'),
    ('CUE2POPS', 'krHACKen', 'VCD format (header layout, CDRWIN pregap fix) reimplemented from its description'),
    ('PS1 USB / SMB Mass Converter Tool v1.0', 'Eliminator14',
     'APPS/POPS layout, identifier rules and title.cfg format (observed output reproduced)'),
    ('Title-CFG Maker', 'El_Isra (israpps)', 'title.cfg approach the converter is built on'),
    ('VMC and MultiDisc Creator v1.0', 'Eliminator14', 'VMC, DISCS.TXT and VMCDIR.TXT generation (observed output reproduced)'),
    ('BDMAssault', 'El_Isra (israpps)', 'exFAT/BDM USB drivers for POPStarter (installed on the memory card)'),
    ('POPStarter Fixes', 'Hugopocked', 'per-game fixes (CHEATS.TXT, PATCH_n.BIN, TROJAN_n.BIN) applied from your copy of the pack'),
    ('PSXVCD', '—', 'VCD converter used as a reference by the community'),
    ('Open PS2 Loader (OPL)', 'ps2homebrew / OPL team', 'Apps menu and title.cfg support'),
]
LIBRARIES = [
    ('Qt for Python (PySide6)', 'LGPLv3', 'https://www.qt.io/qt-for-python'),
    ('py7zr', 'LGPL-2.1', 'https://github.com/miurahr/py7zr'),
    ('PyInstaller (build only)', 'GPLv2 with bootloader exception', 'https://pyinstaller.org'),
]


def html(language: str = 'en') -> str:
    intro = _INTRO.get(language, _INTRO['en'])
    credits_title, libs_title = _HEADINGS.get(language, _HEADINGS['en'])
    rows = ''.join(f'<li><b>{name}</b> — {author}<br><small>{what}</small></li>' for name, author, what in CREDITS)
    libs = ''.join(f'<li><a href="{url}">{name}</a> — {lic}</li>' for name, lic, url in LIBRARIES)
    return (f'<h2>POPS Manager {__version__}</h2><p>{intro}</p>'
            f'<h3>{credits_title}</h3><ul>{rows}</ul><h3>{libs_title}</h3><ul>{libs}</ul>'
            '<p><small>PlayStation is a trademark of Sony Interactive Entertainment. '
            'This project is not affiliated with Sony.</small></p>')
