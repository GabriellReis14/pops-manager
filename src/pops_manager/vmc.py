"""Virtual memory cards and multi-disc files, as created by "VMC and MultiDisc Creator" v1.0
(Eliminator14). Observed by running it on dummy VCDs:

    POPS/<ID>/SLOT0.VMC, SLOT1.VMC     blank formatted PS1 memory cards (128 KiB)
    multi-disc games D1_X, D2_X, ...:
      POPS/D1_X/SLOT0.VMC, SLOT1.VMC   only for disc 1
      POPS/Dn_X/DISCS.TXT              "D1_X.VCD\\r\\nD2_X.VCD\\r\\n..." in every disc folder
      POPS/Dn_X/VMCDIR.TXT             "D1_X" (no newline) in every disc folder: saves are shared

POPStarter cannot create files on USB, so these must exist before the first boot to save games.
The card image is generated from the public PS1 memory card format, not copied from the tool.
"""
from __future__ import annotations
import re

VMC_SIZE = 128 * 1024
FRAME = 128
VMC_SLOTS = ('SLOT0.VMC', 'SLOT1.VMC')
DISC_RE = re.compile(r'^D(\d+)_(.+)$')


def _frame(data: bytes) -> bytes:
    """128-byte frame whose last byte is the XOR of the first 127."""
    body = data.ljust(FRAME - 1, b'\x00')
    checksum = 0
    for byte in body:
        checksum ^= byte
    return body + bytes([checksum])


def blank_vmc() -> bytes:
    """Formatted, empty PS1 memory card (header, 15 free directory frames, 20 unused broken-sector frames)."""
    card = bytearray(VMC_SIZE)
    card[0:FRAME] = _frame(b'MC')
    for i in range(1, 16):                       # directory: block free (0xA0), no next block
        card[i * FRAME:(i + 1) * FRAME] = _frame(b'\xa0' + b'\x00' * 7 + b'\xff\xff')
    for i in range(16, 36):                      # broken sector list: none
        card[i * FRAME:(i + 1) * FRAME] = _frame(b'\xff\xff\xff\xff' + b'\x00' * 4 + b'\xff\xff')
    return bytes(card)


def disc_info(slug: str) -> tuple[int, str] | None:
    """('D2_Fin_Fan_VII') -> (2, 'Fin_Fan_VII'); None for single-disc identifiers."""
    match = DISC_RE.match(slug)
    return (int(match[1]), match[2]) if match else None


def multidisc_groups(slugs: list[str]) -> dict[str, list[str]]:
    """Groups D<n>_<base> identifiers by base, ordered by disc number (like the original tool)."""
    groups: dict[str, list[tuple[int, str]]] = {}
    for slug in slugs:
        info = disc_info(slug)
        if info:
            groups.setdefault(info[1].casefold(), []).append((info[0], slug))
    return {base: [s for _, s in sorted(items)] for base, items in groups.items()}


def discs_txt(discs: list[str]) -> str:
    return ''.join(f'{d}.VCD\r\n' for d in discs)


def vmcdir_txt(discs: list[str]) -> str:
    return discs[0]
