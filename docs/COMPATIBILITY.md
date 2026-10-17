# Compatibility notes

POPS Manager reimplements, in its own code, the output of three community tools and the formats they rely on.
Everything marked **observed** was obtained by running the original program in a temporary folder with dummy
files and comparing the result byte by byte; **documented** facts come from the POPStarter wiki (Shaolin Assassin,
archived copies of `bitbucket.org/ShaolinAssassin/popstarter-documentation-stuff/wiki`) or from source code.

## 1. PS1 USB Mass Converter Tool v1.0 (Eliminator14, built on El_Isra's Title-CFG Maker) — observed

Run from inside `POPS/` next to `POPSTARTER.ELF`; for every `*.VCD` it

1. builds an identifier `<ID>` from the file name and **renames the VCD in place** to `POPS/<ID>.VCD`;
2. creates `APPS/XX.<ID>/XX.<ID>.ELF` (byte-identical copy of `POPSTARTER.ELF`) and
   `APPS/XX.<ID>/title.cfg` = `title=<name>\r\nboot=XX.<ID>.ELF\r\n`.

POPStarter finds the VCD from its own name: `XX.<ID>.ELF` → `mass:/POPS/<ID>.VCD` (`XX.` = USB, `SB.` = SMB).
The `XX.` prefix and the `.VCD` extension must be **upper case** (documented).

| Input file name | Original `<ID>` | POPS Manager `<ID>` |
|---|---|---|
| `Tony Hawk's Pro Skater (USA).VCD` | `Tony_Hawks_Pro_Skater` | same |
| `Tony Hawk's Pro Skater 2 (USA).VCD` | — **skipped silently** (cut to 22 chars, collides) | `Tony_Hawks_Pro_Skate_2` |
| `Castlevania - Symphony of the Night (USA).VCD` | `Castlevania_Symphony_o` | same |
| `Legend of Dragoon, The (USA).VCD` | `Legend_of_Dragoon_The` | same |
| `Final Fantasy VII (USA) (Disc 1).VCD` | `D1_Fin_Fan_VII` | same |
| `Final Fantasy VIII (Disc 1)` | `D1_Fin_Fan_VII` (**collides with VII**) | `D1_Fin_Fan_VIII` |
| `Pokémon Stadium - Edição Ação!.VCD` | `Pokmon_Stadium_Edio_Ao` | `Pokemon_Stadium_Edicao` |

**Identifier length.** The original cuts identifiers at 22 characters, but that is not a POPStarter limit: a
23-character VCD (`Tony_Hawks_Pro_Skater_2`) boots, and the POPStarter documentation allows 85-character names in
`DISCS.TXT`. POPS Manager therefore uses full names by default, up to a conservative 48 characters, with full words
for multi-disc games (`D1_Final_Fantasy_VII`). The setting *Short names* reproduces the original rules exactly (the
table above, and `tests/test_compat_original.py`), which keeps existing saves in `POPS/<ID>/` visible when a device
was prepared with the original converter.

## 2. VMC and MultiDisc Creator v1.0 (Eliminator14) — observed

For every `POPS/*.VCD` it creates, unless they already exist:

| File | Content |
|---|---|
| `POPS/<ID>/SLOT0.VMC`, `SLOT1.VMC` | blank formatted PS1 memory card, 131072 bytes, MD5 `d8f29ffd55cb1e4f77987a1e07472d66` |
| `POPS/D<n>_<X>/DISCS.TXT` (every disc) | `D1_<X>.VCD\r\nD2_<X>.VCD\r\n…` |
| `POPS/D<n>_<X>/VMCDIR.TXT` (every disc) | `D1_<X>` (no newline) — all discs share disc 1's cards |

For multi-disc games, cards are created only in disc 1's folder. POPS Manager generates the card from the public
PS1 memory card format (`vmc.blank_vmc`, identical MD5) and the text files exactly as above; the whole tree was
compared byte by byte with the tool's output. Documented limits: at most 4 lines in `DISCS.TXT`; `VMCDIR.TXT` is a
single line naming a folder inside `POPS`.

POPStarter also creates `SLOT0/1.VMC` by itself on first boot (documented); pre-creating them is harmless and
existing cards are never replaced.

## 3. VCD format (CUE2POPS v2.0, krHACKen) — implemented from its description

A VCD is a 1 MiB header followed by the raw 2352-byte sectors of the disc:

| Offset | Content |
|---|---|
| `0x00` | A0 point: `41 00 A0 00 00 00 00 01 20 00` (data, first track 1, CD-XA) |
| `0x0A` | A1 point: control of the last track (`41` data / `01` audio), last track number (BCD) at `0x11` |
| `0x14` | A2 point: control of the last track, lead-out MSF (BCD) at `0x1B` = sectors + 150 |
| `0x1E` + 10·n | track n: control, 0, number, INDEX 00 MSF, 0, INDEX 01 MSF — every MSF +2 s (track 1 INDEX 00 = 0) |
| `0x400` | `6B 48 6E 22` ("kHn" + format version; PSXVCD writes `22`, CUE2POPS v2.0 `20`) |
| `0x408`, `0x40C` | sector count, uint32 little-endian, twice |

- Track 1 must be `MODE2/2352`. A CDRWIN-style cue (exactly one `PREGAP`, no `POSTGAP`) gets 150 blank sectors
  before the first audio track and the following tracks shifted by another 2 s, as CUE2POPS does.
- CUE2POPS refuses multi-file cues (one `.bin` per track); POPS Manager joins them in order, which gives exactly the
  same VCD as a merged `.bin` (tested).
- 2048-byte `.iso` files are **refused**: POPStarter needs raw 2352-byte sectors (documented: "POPS doesn't
  support PS1 games images as .iso"), and the XA audio/video sectors cannot be rebuilt from a 2048-byte ISO.
  A raw image named `.iso`/`.img` is accepted.
- `.zip` and `.7z` archives with one disc are extracted to a temporary folder first.
- **Compared with PSXVCD:** converting *Tony Hawk's Pro Skater (USA)* (`.zip` with `.bin`/`.cue`) gives a VCD
  byte-identical to the one made by PSXVCD (661,864,144 bytes), which boots on a PS2. Games with audio tracks
  or CDRWIN pregaps have only been checked against the format description and synthetic images.

## 4. Shared files

| Source (your resources) | Device | Notes |
|---|---|---|
| `POPS/POPSTARTER.ELF` | copied into every `APPS/XX.<ID>/` and to `POPS/` | |
| `POPS/POPS_IOX.PAK` | `POPS/POPS_IOX.PAK` | required in `mass:/POPS/` (documented) |
| `POPS/CHEATS.TXT`, `POPS/IGR_*.TM2`, other files | `POPS/` (names upper-cased) | `CHEATS.TXT` in `POPS/` applies to all games; one in `POPS/<ID>/` applies to that game. IGR textures are read from `POPS/` only. |
| `.exe`/`.dll` in the POPS folder | not copied (option) | Windows converters and MinGW DLLs; useless on a PS2 |
| `POPSTARTER/usbd.irx`, `usbhdfsd.irx` | **not copied by default** | see below |

Existing files on the device are never replaced, even if they are a different version.

## 5. Game fixes (Hugopocked POPStarter Fixes)

POPStarter reads `CHEATS.TXT`, `PATCH_n.BIN` (compatibility modes) and `TROJAN_n.BIN` (code patches) from the
game's folder `POPS/<ID>/` (documented). The pack has one folder per game in `POPS Game Fixes`:

| Pack layout | Applied |
|---|---|
| `<Title> [All versions]/` files | automatically |
| `<Title>/<Title (Region) (Languages) [vX.Y]>/` files | automatically, when region/languages/version match the game file name (a file without a version tag counts as v1.0) |
| `CHEATS Europe.TXT`, `USA Ver CHEATS.TXT` | as `CHEATS.TXT` when the region matches |
| deeper sub-folders (`16-9`, `4-3`, `Arcade`…) | offered as variants in *Fixes...* |
| `*.xdelta`, `*.ppf` | never: they patch the disc image; the user is told to apply them before adding the game |

Matching ignores punctuation, accents, `The` placement and bracketed tags; all 108 game folders of the
2023-08-11 pack match their own names. Existing files in `POPS/<ID>/` are never replaced. `POPS General Fixes`
(overclock, GTE, dithering…) and `Compatibility_Modes` (`PATCH_1..7.BIN`, one at a time) are only added by the user.
For multi-disc games the fixes are copied to every disc's folder.

## 6. USB drivers, FAT32 and exFAT

- The documented USB requirements are a **FAT12/16/32** partition and **defragmented** VCDs. NTFS is not supported.
- **exFAT** works only with the BDM drivers from **BDMAssault** (El_Isra): `bdm_assault.irx` installed as
  `usbd.irx` and `usbd_bd_assault.irx` as `usbhdfsd.irx`, in **`mc0:/POPSTARTER/`** (memory card; `mc1:` as
  fallback). POPStarter r13 "no longer loads usbd.irx and usbhdfsd.irx from mass" — a `POPSTARTER` folder on the
  USB drive has no effect. The `usbd.irx`/`usbhdfsd.irx` pair in your resources is most likely BDMAssault.
- **MBR vs GPT and 4K sectors are not documented**; the classic drivers expect MBR and 512-byte sectors.
  Observed with BDMAssault on the memory card: a **GPT** FAT32 flash drive works.
- **USB-to-NVMe enclosures — observed failure.** An NVMe SSD in a Realtek RTL9210 enclosure, FAT32 (valid boot
  sector, 32 KiB clusters, MBR, contiguous VCDs): OPL lists the games, but every POPStarter game flashes the screen
  and returns to OPL. The *same files* start from a SanDisk flash drive (FAT32, GPT) and from a 2.5" HDD in a
  JMicron SATA enclosure (exFAT). Likely cause: the 500 mA PS2 port and/or the bridge's slow re-enumeration when
  POPStarter resets the IOP and reloads the USB drivers (not proven). *Check device* warns about NVMe bridges
  (RTL9210/9220, JMS581/583, ASM2362/2364/2464). A Y cable or powered hub may help; a flash drive or SATA
  enclosure is the safe choice.
- *Tools → Check device* reports the file system, partition style, cluster/sector size and the fragmentation of
  every VCD (`FSCTL_GET_RETRIEVAL_POINTERS`, read-only). After each installation the new VCDs are checked too.
- On Windows the copy uses `CopyFileExW`, which reserves the file size before writing; this helps keep VCDs
  contiguous on a drive with enough free contiguous space, but does not defragment existing files.

"Screen flashes and returns to OPL" has no documented single cause. Things to check: a missing/wrong
`POPS_IOX.PAK`, ELF and VCD names that do not match, lower-case `.vcd`, a fragmented VCD, a GPT or 4K-sector
drive, exFAT without BDMAssault, or a mismatching `usbd.irx`/`usbhdfsd.irx` on the memory card.

## 7. Not yet verified

- PS2 hardware tests of: converted VCDs, UTF-8 accents in `title.cfg`, multi-disc swapping, POPS files copied with
  upper-cased names.
- The longest identifier POPStarter/OPL accept (48 is a conservative choice); GPT/4K-sector support without BDM;
  line endings required by `DISCS.TXT`; the effect of each fix on hardware (they come from the pack as-is).

## Repeating the comparisons

```powershell
$env:POPS_ORIGINAL_DIR = 'C:\folder\with\PS1_USB_Converter.exe and VMC and MultiDisc Creator.exe'
.venv\Scripts\python.exe -m pytest tests/test_compat_original.py -v -s
```

The originals run on copies inside a temporary directory; the folder you point to is not modified.
