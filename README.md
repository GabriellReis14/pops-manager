# POPS Manager — community prototype v0.2.0

Open-source Python/PySide6 tool that prepares PS1 games for **POPStarter + OPL Apps** on a USB flash drive or external HDD, in one step: convert to VCD, copy, create the OPL launcher, memory cards and multi-disc files.

It replaces the separate `PS1_USB_Converter.exe`, `VMC and MultiDisc Creator.exe` and a VCD converter, reproducing their output (verified byte by byte against the originals, see [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)). **Experimental: the converted VCDs have not been tested on PS2 hardware yet.** No games or third-party POPStarter binaries are provided.

## Features

- Add games from any folder (button or drag and drop): `.VCD`, `.CUE` + `.BIN` (also one `.bin` per track), raw `.BIN`/`.ISO`/`.IMG`, `.ZIP` and `.7Z`.
- Conversion to VCD (byte-identical to PSXVCD for a tested game) in a temporary folder, deleted at the end. Up to 3 games are converted **in parallel** while the current one is written to the device; writing stays one game at a time so VCDs are not fragmented. The progress bar shows write speed and time left, and warns when the device itself is slow.
- Per-game status and progress in the list; finished games are kept if you cancel; a failed game does not stop the others.
- Final structure shown as a tree before writing (new / kept / conflict); short confirmation.
- OPL Apps launcher (`APPS/XX.<ID>/`) with full, readable identifiers (`Tony_Hawks_Pro_Skater_2`, up to 48 characters), or short 22-character names like the original converter (setting) — without its *Tony Hawk's Pro Skater 2/3/4* collision.
- **Game fixes**: if you have the *Hugopocked POPStarter Fixes* pack (`POPS/POPSUtils`), each added game gets its fixes automatically (`CHEATS.TXT`, `PATCH_n.BIN`, `TROJAN_n.BIN`, matched by name, region and version). The *Fixes...* window shows them and lets you add variants (16:9…), compatibility modes, general fixes or your own files.
- Optional: blank memory cards (`SLOT0/1.VMC`) and multi-disc `DISCS.TXT`/`VMCDIR.TXT`, also as a separate tool for games already on the device.
- Copies your `POPS` folder contents (`POPS_IOX.PAK`, `CHEATS.TXT`, `IGR_*.TM2`…) when missing.
- *Tools → Check device*: file system, MBR/GPT, cluster/sector size and **VCD fragmentation** (read-only).
- Never overwrites anything on the device; Portuguese, English and Spanish interface.

## Requirements

- Windows 10/11 x64 (Linux/macOS may run from source; device checks and fast copy are Windows-only)
- To run from source: Python 3.10+ (tested on 3.10 and 3.14)
- PS1 games you are authorized to use, as raw BIN/CUE dumps or VCDs (2048-byte ISOs cannot be used)
- Your own `POPSTARTER.ELF` and `POPS_IOX.PAK` — see [POPStarter files](#popstarter-files)
- A **FAT32** drive (exFAT only with BDMAssault on the memory card, see below), VCDs **defragmented**

## Run from source

```powershell
.\scripts\setup_dev.ps1     # creates .venv and installs the project + dev tools (uses uv if installed)
.\scripts\run.ps1           # starts the app (works from any current directory)
```

Manual equivalent: `py -m venv .venv`, `.venv\Scripts\activate`, `pip install -e ".[dev]"`, `pops-manager`.
In VS Code, select `.venv` as the interpreter; *Run and Debug → POPS Manager* and the Testing panel are preconfigured.

## How to use

1. **Add games** (or drag files/folders onto the window). Files that cannot be used show **✖ Error** — hover it to see why; they are skipped.
2. Optionally edit the OPL name and the identifier (letters, digits, `_`, max. 48). Check the **Fixes** column; double-click it to change a game's fixes.
3. Choose the **destination** (drive root). Check the tree: green = new, grey = already there and kept, red = conflict.
4. Check the **POPStarter files** line (✔ = found) and the VMC / multi-disc options.
5. Click **Prepare PS2**, confirm, and follow the progress of each game.
6. Run *Tools → Check device* if a game does not start, then test on the PS2 before touching a working setup.

Result on the drive:

```
USB_ROOT/
├── APPS/
│   ├── XX.Tony_Hawks_Pro_Skater_2/
│   │   ├── XX.Tony_Hawks_Pro_Skater_2.ELF   copy of POPSTARTER.ELF
│   │   └── title.cfg                        title=Tony Hawk's Pro Skater 2 / boot=XX.Tony_Hawks_Pro_Skater_2.ELF
│   ├── XX.D1_Final_Fantasy_VII/ …
│   └── XX.D2_Final_Fantasy_VII/ …
└── POPS/
    ├── POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2  from your POPS folder, only if missing
    ├── Tony_Hawks_Pro_Skater_2.VCD
    ├── Tony_Hawks_Pro_Skater_2/  SLOT0.VMC, SLOT1.VMC, CHEATS.TXT, PATCH_1.BIN, TROJAN_0.BIN …  (cards + fixes)
    ├── D1_Final_Fantasy_VII.VCD, D2_Final_Fantasy_VII.VCD
    ├── D1_Final_Fantasy_VII/  SLOT0.VMC, SLOT1.VMC, DISCS.TXT, VMCDIR.TXT
    └── D2_Final_Fantasy_VII/  DISCS.TXT, VMCDIR.TXT  (saves shared with disc 1)
```

Why the VCDs are not in one folder per game: POPStarter derives the VCD from its own ELF name and only looks in `POPS/` (or `POPS0`…`POPS9`), so the VCDs must stay there. Everything else that belongs to a game (memory cards, fixes) is in its own `POPS/<ID>/` folder, and the launcher in `APPS/XX.<ID>/`.

## Speed

The PC side is fast (a 660 MB game converts in a few seconds, and the next games are converted while the current one is written). The device is usually the limit: USB 2.0 flash drives often write 5–20 MB/s, so a 700 MB game can take one minute or more. The progress bar shows the real speed and the time left. Writing several games at once would not be faster on a flash drive and would fragment the VCDs, which POPStarter cannot read.

## FAT32, exFAT and "the screen flashes and goes back to OPL"

- POPStarter's own USB drivers read **FAT32** (MBR, 512-byte sectors) and need every VCD in **one contiguous block**. A fragmented VCD is a classic cause of the game flashing and returning to OPL. *Check device* lists fragmented VCDs; the fix is to copy everything to a freshly formatted drive (or defragment).
- **exFAT** works only with the **BDMAssault** drivers (El_Isra) installed on the **memory card** as `mc0:/POPSTARTER/usbd.irx` and `usbhdfsd.irx`. POPStarter r13 does not load these drivers from the USB drive, so a `POPSTARTER` folder on the drive has no effect (POPS Manager does not copy it unless you enable it).
- With BDMAssault on the memory card, POPStarter uses those drivers for every drive (a GPT flash drive also worked in our tests); if one drive works and another does not, compare them with *Check device*.
- **Avoid NVMe SSDs in USB enclosures** (e.g. Realtek RTL9210): OPL lists the games, but POPStarter games flash and return to OPL, while the same files work from a flash drive or a SATA HDD/SSD enclosure. *Check device* warns about these bridges.

## POPStarter files

POPS Manager needs `POPSTARTER.ELF` and normally `POPS_IOX.PAK`. **They are not included in this repository or in public releases**: POPStarter is closed-source freeware and `POPS_IOX.PAK` contains Sony's POPS emulator. Use your own copies. A resources folder has the same layout as the drive:

```
<resources>/POPS/POPSTARTER.ELF, POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2 …
<resources>/POPSTARTER/…            (optional; normally belongs on the memory card)
```

The fixes pack is optional: put it in `<resources>/POPS/POPSUtils/` (the `POPS Game Fixes`, `POPS General Fixes` and `Compatibility_Modes` folders are found at any depth) or choose its folder in *Settings*. Disc image patches (`.xdelta`/`.ppf`) in the pack cannot be applied by copying files: the *Fixes...* window points to them so you can patch the image (e.g. with DeltaPatcher) before adding the game.

They are found automatically, in this order: files chosen in *Settings → POPStarter files* (saved per user) → files embedded in a personal build → a `resources` folder next to `POPS-Manager.exe` → the project root when running from source (`POPS/`, `POPSTARTER/`, ignored by git). Windows programs in the POPS folder (`.exe`, `.dll`) are not copied unless you enable it. Files already on the drive are never replaced.

## Test

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests use temporary folders, fake files and small synthetic disc images; GUI tests run headless (Qt `offscreen`). Optional tests run your copies of the original tools and compare their output — see [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md#repeating-the-comparisons).

## Packaging a Windows executable

```powershell
.\scripts\build_windows.ps1                    # tests, PyInstaller onedir build, smoke test of the exe
.\scripts\build_windows.ps1 -Zip               # also dist\POPS-Manager-<version>-win64.zip
.\scripts\build_windows.ps1 -BundleResources   # PERSONAL build: embeds your POPS folder files, POPSTARTER\ and POPSUtils fixes
```

The portable app is generated in `dist\POPS-Manager\` (run `POPS-Manager.exe`; keep `_internal` next to it). The script checks the bundled translations, 7z support and (personal build) embedded files by starting the exe in a headless smoke-test mode. A personal build writes `PERSONAL_BUILD_DO_NOT_DISTRIBUTE.txt`: **never publish or share it**; `-Zip` is refused for it.

## Project layout

```
src/pops_manager/core.py         names, layout plan, validation, per-game install with rollback (no Qt)
src/pops_manager/convert.py      CUE/BIN/ISO/ZIP/7Z -> VCD (CUE2POPS format)
src/pops_manager/vmc.py          blank memory cards, DISCS.TXT / VMCDIR.TXT
src/pops_manager/fixes.py        matches games with a fix pack (Hugopocked POPStarter Fixes layout)
src/pops_manager/copyfile.py     exclusive copy with progress (CopyFileExW on Windows)
src/pops_manager/diagnostics.py  read-only device checks and fragmentation
src/pops_manager/resources.py    finds your POPStarter files
src/pops_manager/main.py         PySide6 window;  i18n.py  PT/EN/ES texts;  credits.py  About dialog
tests/                           pytest suite
scripts/                         setup_dev.ps1, run.ps1, build_windows.ps1, stage_fixes.py
docs/COMPATIBILITY.md            observed behaviour of the original tools, formats and limitations
```

## Credits

POPS Manager stands on the work of the PS2 scene. It reimplements, in its own code, the behaviour of:

- **POPStarter** — krHACKen (documentation by Shaolin Assassin)
- **CUE2POPS** — krHACKen (VCD format)
- **PS1 USB / SMB Mass Converter Tool** and **VMC and MultiDisc Creator** — Eliminator14
- **Title-CFG Maker** and **BDMAssault** — El_Isra (israpps)
- **POPStarter Fixes** — Hugopocked (per-game fixes, used from your copy of the pack)
- **PSXVCD** — VCD converter used as a reference by the community
- **Open PS2 Loader** — ps2homebrew / OPL team

Libraries: Qt for Python/PySide6 (LGPLv3), py7zr (LGPL-2.1); PyInstaller for builds. The same list is in *Help → About and credits*.

## Contributing

Please open issues with sanitized folder trees, the *Check device* report, application version, OPL/POPStarter version and the observed result. Never attach copyrighted game images, BIOS or proprietary third-party binaries (the `.gitignore` excludes `POPS/`, `POPSTARTER/`, `resources/`, `APPS/`, `*.VCD`, `*.ELF`, `*.PAK`, `*.IRX` and disc images).

## Status

- ✅ Conversion to VCD (BIN/CUE, multi-file cues, raw ISO/IMG, ZIP, 7Z) — **not yet tested on hardware**
- ✅ OPL Apps layout, identifiers and title.cfg identical to the original converter (minus its collisions)
- ✅ VMC and multi-disc files identical to the original creator
- ✅ Per-game progress, parallel conversion, speed/time left, cancel, skip invalid files, never overwrite; device check with fragmentation and NVMe-enclosure warning
- ✅ Automatic per-game fixes from the Hugopocked pack, plus manual variants/compatibility modes/general fixes
- ⏳ SMB mode, VCD ↔ PSXVCD/CUE2POPS hardware comparison, defragmenting copy, multi-disc archives

Copyright © contributors. Original project code under MIT; no rights claimed in POPStarter, OPL or the tools credited above.
