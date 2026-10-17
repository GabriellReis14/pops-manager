from pathlib import Path
import pytest

# Minimal 32-bit little-endian MIPS ELF header: enough for is_ps2_elf(), not a real program.
FAKE_ELF = b'\x7fELF\x01\x01\x01' + b'\x00' * 9 + b'\x02\x00\x08\x00' + b'FAKE_POPSTARTER' * 4


@pytest.fixture
def elf(tmp_path: Path) -> Path:
    path = tmp_path / 'tools' / 'POPSTARTER.ELF'
    path.parent.mkdir()
    path.write_bytes(FAKE_ELF)
    return path


@pytest.fixture
def usb(tmp_path: Path) -> Path:
    root = tmp_path / 'usb'
    root.mkdir()
    return root


@pytest.fixture
def make_vcd(tmp_path: Path):
    def make(relative: str, content: bytes | None = None) -> Path:
        path = tmp_path / 'library' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if content is not None else f'VCD:{relative}'.encode())
        return path
    return make
