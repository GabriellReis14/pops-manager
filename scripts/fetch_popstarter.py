"""Downloads the official POPStarter r13 Beta (2019/06/05) package, checks it and extracts POPSTARTER.ELF
for the public build. The binary is never committed to the repository.

    python scripts/fetch_popstarter.py <output folder> [--zip <local copy of the package>]

POPStarter is freeware by krHACKen (closed source, project abandoned by its author). It is redistributed
unmodified, with credit; POPS_IOX.PAK (Sony's emulator) is never included.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import io
import sys
import urllib.request
import zipfile

URL = 'https://archive.org/download/popstarter-r-13-beta-20190605/POPStarter_r13_Beta_20190605.zip'
ZIP_SHA1 = '1b176d6c3e8fecda5a3cfa24641825203a50a257'          # published by archive.org
ELF_MEMBER = 'POPStarter_r13_Beta_20190605/POPSTARTER.ELF'
CHANGES_MEMBER = 'POPStarter_r13_Beta_20190605/CHANGES.TXT'
ELF_SHA256 = '734c813e8e8ec2c6729ec5e15dd46ab696e90deeade8d0b2ca3ad03782781aa1'   # also tested on a PS2

NOTICE = f"""POPStarter
==========

POPSTARTER.ELF - POPStarter Revision 13 Beta (2019/06/05)
Author: krHACKen (kHn). Documentation: Shaolin Assassin.
Freeware, closed source; redistributed here unmodified, with credit to its author.
Source: {URL}
SHA-256: {ELF_SHA256}
CHANGES.TXT is the author's original changelog.

POPS Manager does NOT include POPS_IOX.PAK: it contains Sony's POPS emulator, which cannot be
redistributed. Use your own copy (see the README).

PlayStation is a trademark of Sony Interactive Entertainment. POPS Manager is not affiliated with Sony or
with the authors of POPStarter.
"""


def fetch(out: Path, local_zip: Path | None = None) -> Path:
    data = local_zip.read_bytes() if local_zip else urllib.request.urlopen(URL, timeout=120).read()
    if hashlib.sha1(data).hexdigest() != ZIP_SHA1:
        raise SystemExit('POPStarter package checksum does not match; refusing to use it.')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        elf = z.read(ELF_MEMBER)
        changes = z.read(CHANGES_MEMBER)
    if hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise SystemExit('POPSTARTER.ELF checksum does not match; refusing to use it.')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'POPSTARTER.ELF').write_bytes(elf)
    (out / 'CHANGES.TXT').write_bytes(changes)
    (out / 'NOTICE.TXT').write_text(NOTICE, encoding='utf-8')
    return out / 'POPSTARTER.ELF'


if __name__ == '__main__':
    args = sys.argv[1:]
    local = Path(args[args.index('--zip') + 1]) if '--zip' in args else None
    print(f'POPStarter verified: {fetch(Path(args[0]), local)}')
