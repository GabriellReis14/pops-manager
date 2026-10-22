<p align="center"><img src="src/pops_manager/assets/icon.png" width="96" alt="POPS Manager icon"></p>

# POPS Manager

**English** · [Português](README.pt-BR.md)

Open-source Windows tool that prepares PS1 games for **POPStarter + OPL Apps** on a USB flash drive or external HDD, in one step: convert to VCD, copy, create the OPL launcher, memory cards, multi-disc files and game fixes.

It replaces the separate `PS1_USB_Converter.exe`, `VMC and MultiDisc Creator.exe` and a VCD converter (PSXVCD/CUE2POPS), reproducing their output byte by byte (see [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)). Tested on a PS2 Slim with OPL and POPStarter r13. No games or third-party POPStarter binaries are provided.

## Download

1. Open the [**Releases**](../../releases/latest) page and download `POPS-Manager-<version>-win64.zip`.
2. Extract it to a short path (e.g. `C:\POPS-Manager`) and run `POPS-Manager.exe` (Windows 10/11 x64).
3. Provide your own POPStarter files (see [POPStarter files](#popstarter-files)).

Windows SmartScreen may warn about an unknown publisher because the executable is not code-signed: choose *More info → Run anyway*, or build it yourself from source.

## Features

- Add games from any folder (button or drag and drop): `.VCD`, `.CUE` + `.BIN` (also one `.bin` per track), raw `.BIN`/`.ISO`/`.IMG`, `.ZIP` and `.7Z`.
- Conversion to VCD (byte-identical to PSXVCD) in a temporary folder, deleted at the end. Up to 3 games are converted **in parallel** while the current one is written; writing stays one game at a time so VCDs are not fragmented. The progress bar shows write speed and time left, and warns when the device itself is slow.
- Per-game status and progress; finished games are kept if you cancel; a failed game does not stop the others.
- The final structure is shown as a tree before writing (new / kept / conflict).
- OPL Apps launcher (`APPS/XX.<ID>/`) with full, readable names (`Tony_Hawks_Pro_Skater_2`, up to 48 characters), or short 22-character names like the original converter — without its *Tony Hawk's Pro Skater 2/3/4* collision.
- **Game fixes**: with the *Hugopocked POPStarter Fixes* pack, each game gets its fixes automatically (`CHEATS.TXT`, `PATCH_n.BIN`, `TROJAN_n.BIN`, matched by name, region and version). The *Fixes...* window adds variants (16:9…), compatibility modes, general fixes or your own files.
- Blank memory cards (`SLOT0/1.VMC`) and multi-disc `DISCS.TXT`/`VMCDIR.TXT`, also as a separate tool for games already on the device.
- Copies your `POPS` folder contents (`POPS_IOX.PAK`, `CHEATS.TXT`, `IGR_*.TM2`…) when missing.
- *Tools → Check device*: model, file system, MBR/GPT, cluster/sector size, **VCD fragmentation** and **NVMe enclosure** warning (read-only).
- Never overwrites anything on the device. Interface in Portuguese, English and Spanish.

## How to use

1. **Add games** (or drag files/folders onto the window). Files that cannot be used show **✖ Error** — hover it to see why; they are skipped.
2. Optionally edit the OPL name and the identifier (letters, digits, `_`, max. 48). Check the **Fixes** column; double-click it to change a game's fixes.
3. Choose the **destination** (drive root). Check the tree: green = new, grey = already there and kept, red = conflict.
4. Check the **POPStarter files** line (✔ = found) and the VMC / multi-disc options.
5. Click **Prepare PS2**, confirm, and follow the progress of each game.
6. If a game does not start, run *Tools → Check device* and read [Compatible drives](#compatible-drives).

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

The VCDs cannot be moved into one folder per game: POPStarter derives the VCD from its own ELF name and only looks in `POPS/` (or `POPS0`…`POPS9`). Everything else that belongs to a game is in its own `POPS/<ID>/` folder, and the launcher in `APPS/XX.<ID>/`.

## Compatible drives

### Avoid NVMe SSDs in USB enclosures (e.g. Realtek RTL9210)

An NVMe SSD in a USB enclosure with a **Realtek RTL9210** bridge, formatted correctly as FAT32, **lists the games in OPL, but every POPStarter game flashes the screen and returns to OPL**. The same files start normally from a cheap USB flash drive and from a 2.5" HDD in a SATA enclosure. Everything else was identical (VCDs, launchers, POPStarter files, partition, no fragmentation).

Why: OPL reads the drive with its own driver, which is already running. When a game starts, POPStarter resets the PS2's I/O processor and loads its USB drivers again, so the drive has to be recognised a second time. NVMe enclosures draw more power than the PS2's USB port provides (500 mA) and are slow to answer after that reset, so POPStarter does not find the VCD and goes back to OPL.

What to do:

- Prefer a **USB flash drive** or a **SATA HDD/SSD in a USB enclosure** (JMicron or ASMedia SATA bridges worked).
- If you want to try an NVMe enclosure anyway, connect it with a **Y cable** (both PS2 USB ports) or through a **powered USB hub**.
- *Tools → Check device* shows the drive's model and warns about NVMe bridges (RTL9210/RTL9220, JMS581/JMS583, ASM2362/ASM2364/ASM2464).

### File system, partition and fragmentation

- **FAT32** is the standard for POPStarter. Windows only offers NTFS/exFAT for drives over 32 GB in the format window; recent Windows 11 versions can format larger drives as FAT32 from the command line (`format X: /FS:FAT32 /Q`), and third-party formatters also work. The result was verified to be correct.
- **exFAT** works only with the **BDMAssault** drivers (El_Isra) installed on the **memory card** as `mc0:/POPSTARTER/usbd.irx` and `usbhdfsd.irx`. POPStarter r13 does not load these drivers from the USB drive, so a `POPSTARTER` folder on the drive has no effect (POPS Manager does not copy it unless you enable it).
- With BDMAssault on the memory card, a **GPT** flash drive also worked. Without it, use MBR.
- Every VCD must be in **one contiguous block**. A fragmented VCD is another classic cause of the game flashing and returning to OPL. *Check device* lists fragmented VCDs; copy everything to a freshly formatted drive (or defragment).

## Speed

The PC side is fast (a 660 MB game converts in a few seconds, and the next games are converted while the current one is written). The device is usually the limit: USB 2.0 flash drives often write 5–20 MB/s, so a 700 MB game can take a minute or more. Writing several games at once would not be faster and would fragment the VCDs.

## POPStarter files

POPS Manager needs `POPSTARTER.ELF` and normally `POPS_IOX.PAK`. **They are not included in this repository or in the releases**: POPStarter is closed-source freeware and `POPS_IOX.PAK` contains Sony's POPS emulator. Use your own copies. Put them in a `resources` folder next to `POPS-Manager.exe`, with the same layout as the drive, or choose them in *Settings → POPStarter files*:

```
resources/POPS/POPSTARTER.ELF, POPS_IOX.PAK, CHEATS.TXT, IGR_*.TM2 …
resources/POPS/POPSUtils/          optional: Hugopocked POPStarter Fixes
resources/POPSTARTER/…             optional; normally belongs on the memory card
```

Search order: *Settings* → files embedded in a personal build → `resources` next to the exe → the project root when running from source. Windows programs in the POPS folder (`.exe`, `.dll`) are not copied unless you enable it. Disc image patches (`.xdelta`/`.ppf`) from the fixes pack must be applied to the image by hand (e.g. with DeltaPatcher); the *Fixes...* window points to them.

## Run from source

```powershell
.\scripts\setup_dev.ps1     # creates .venv and installs the project + dev tools (uses uv if installed)
.\scripts\run.ps1           # starts the app (works from any current directory)
.venv\Scripts\python.exe -m pytest -q
```

Python 3.10+ (tested on 3.10 and 3.14). In VS Code, select `.venv` as the interpreter; *Run and Debug → POPS Manager* and the Testing panel are preconfigured. Tests use temporary folders, fake files and small synthetic disc images; optional tests compare the output with your copies of the original tools ([docs/COMPATIBILITY.md](docs/COMPATIBILITY.md#repeating-the-comparisons)).

## Building

```powershell
.\scripts\build_windows.ps1                    # tests, PyInstaller onedir build, smoke test of the exe
.\scripts\build_windows.ps1 -Zip               # also dist\POPS-Manager-<version>-win64.zip (what the Releases contain)
.\scripts\build_windows.ps1 -BundleResources   # PERSONAL build with your POPS files, POPSTARTER\ and fixes embedded
```

A personal build writes `PERSONAL_BUILD_DO_NOT_DISTRIBUTE.txt`: **never publish or share it** (`-Zip` is refused for it). Releases are built by GitHub Actions from a version tag, without any third-party file. The icon is original artwork drawn by `scripts/make_icon.py`.

## Project layout

```
src/pops_manager/core.py         names, layout plan, validation, per-game install with rollback (no Qt)
src/pops_manager/convert.py      CUE/BIN/ISO/ZIP/7Z -> VCD
src/pops_manager/vmc.py          blank memory cards, DISCS.TXT / VMCDIR.TXT
src/pops_manager/fixes.py        matches games with a fix pack (Hugopocked POPStarter Fixes layout)
src/pops_manager/copyfile.py     exclusive copy with progress (CopyFileExW on Windows)
src/pops_manager/diagnostics.py  read-only device checks, fragmentation, NVMe bridges
src/pops_manager/resources.py    finds your POPStarter files
src/pops_manager/main.py         PySide6 window;  i18n.py  PT/EN/ES texts;  credits.py  About dialog
tests/                           pytest suite
scripts/                         setup_dev, run, build_windows, stage_fixes, make_icon
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

Libraries: Qt for Python/PySide6 (LGPLv3), py7zr (LGPL-2.1); PyInstaller for builds. The same list is in *Help → About and credits*. PlayStation is a trademark of Sony Interactive Entertainment; this project is not affiliated with Sony.

## Contributing

Pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Issues: please include the *Check device* report, the app version, your OPL/POPStarter version and what happened. Never attach games, BIOS or proprietary third-party binaries.

## Status

- ✅ Tested on PS2 hardware: converted VCDs, OPL launcher, full-length names, game fixes
- ✅ Output identical to PS1_USB_Converter, VMC and MultiDisc Creator and PSXVCD (minus their name collisions)
- ✅ Parallel conversion, per-game progress, speed/time left, cancel, never overwrite; device check
- ⏳ SMB mode, defragmenting copy, multi-disc archives

Copyright © contributors. Original project code under MIT; no rights claimed in POPStarter, OPL or the tools credited above.
