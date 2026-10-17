"""Read-only checks of the destination device (Windows). Nothing here writes to the device."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import ctypes
import os
import shutil
import sys

IS_WINDOWS = sys.platform == 'win32'
_FILE_READ_ATTRIBUTES = 0x80
_SHARE_ALL = 0x7
_OPEN_EXISTING = 3
_FSCTL_GET_RETRIEVAL_POINTERS = 0x00090073
_IOCTL_DISK_GET_PARTITION_INFO_EX = 0x00070048
_IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
_BUS_USB = 7
# USB-to-NVMe bridges. On a PS2 these enclosures may list games in OPL but fail when POPStarter resets the
# IOP and reloads the USB drivers (observed with an RTL9210: game flashes and returns to OPL; the same files
# work from a flash drive). Likely power (500 mA port) and/or slow re-enumeration.
NVME_BRIDGES = ('NVME', 'RTL9210', 'RTL9220', 'JMS583', 'JMS581', 'ASM2362', 'ASM2364', 'ASM2464')
_ERROR_MORE_DATA = 234
_ERROR_HANDLE_EOF = 38
_PARTITION_STYLES = {0: 'MBR', 1: 'GPT', 2: 'RAW'}
_DRIVE_TYPES = {2: 'removable', 3: 'fixed', 4: 'network', 5: 'cdrom', 6: 'ramdisk'}


@dataclass
class DeviceInfo:
    root: Path
    filesystem: str = '?'
    cluster_size: int = 0
    sector_size: int = 0
    partition_style: str = '?'
    drive_type: str = '?'
    total: int = 0
    free: int = 0
    fragmented: dict[str, int] = field(default_factory=dict)   # VCD name -> number of fragments
    vcd_count: int = 0
    model: str = ''              # vendor + product reported by the USB bridge
    usb: bool = False

    def warnings(self) -> list[str]:
        """Neutral, English problem codes; the GUI translates them."""
        codes = []
        if self.filesystem.upper() not in ('FAT32', 'EXFAT', '?'):
            codes.append('fs_unsupported')
        if self.partition_style == 'GPT':
            codes.append('gpt')
        if any(name in self.model.upper() for name in NVME_BRIDGES):
            codes.append('nvme_bridge')
        if self.sector_size and self.sector_size != 512:
            codes.append('sector_size')
        if self.fragmented:
            codes.append('fragmented')
        return codes


def _kernel32():
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    k32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                                    ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    return k32


def _open(k32, path: str):
    handle = k32.CreateFileW(path, _FILE_READ_ATTRIBUTES, _SHARE_ALL, None, _OPEN_EXISTING, 0, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), f'Cannot open {path}')
    return handle


def fragments(path: Path) -> int:
    """Number of non-contiguous pieces of a file on disk (1 = contiguous). Windows only."""
    if not IS_WINDOWS:
        return 1
    k32 = _kernel32()
    handle = _open(k32, str(path))
    try:
        start = ctypes.c_longlong(0)
        out = ctypes.create_string_buffer(64 * 1024)
        returned = ctypes.c_uint32()
        ok = k32.DeviceIoControl(handle, _FSCTL_GET_RETRIEVAL_POINTERS, ctypes.byref(start), 8,
                                 out, len(out), ctypes.byref(returned), None)
        error = ctypes.get_last_error()
        if not ok and error == _ERROR_HANDLE_EOF:     # empty or tiny file stored without clusters
            return 1
        if not ok and error != _ERROR_MORE_DATA:
            raise OSError(error, f'Cannot read the cluster map of {path}')
        count = int.from_bytes(out.raw[0:4], 'little')
        vcn = int.from_bytes(out.raw[8:16], 'little', signed=True)
        pieces, expected = 0, None
        for i in range(min(count, (len(out) - 16) // 16)):
            next_vcn = int.from_bytes(out.raw[16 + i * 16:24 + i * 16], 'little', signed=True)
            lcn = int.from_bytes(out.raw[24 + i * 16:32 + i * 16], 'little', signed=True)
            if lcn != expected:               # adjacent runs are one piece
                pieces += 1
            expected = lcn + (next_vcn - vcn)
            vcn = next_vcn
        return pieces + (1 if not ok else 0)   # MORE_DATA: at least one more piece
    finally:
        k32.CloseHandle(handle)


def device_info(root: Path, check_vcds: bool = True) -> DeviceInfo:
    info = DeviceInfo(root)
    total, _, free = shutil.disk_usage(root)
    info.total, info.free = total, free
    if IS_WINDOWS:
        k32 = _kernel32()
        drive = os.path.splitdrive(os.path.abspath(root))[0]
        volume = drive + '\\'
        name = ctypes.create_unicode_buffer(64)
        if k32.GetVolumeInformationW(volume, None, 0, None, None, None, name, len(name)):
            info.filesystem = name.value
        spc, bps, nfree, ntotal = (ctypes.c_uint32() for _ in range(4))
        if k32.GetDiskFreeSpaceW(volume, ctypes.byref(spc), ctypes.byref(bps), ctypes.byref(nfree), ctypes.byref(ntotal)):
            info.sector_size, info.cluster_size = bps.value, spc.value * bps.value
        info.drive_type = _DRIVE_TYPES.get(k32.GetDriveTypeW(volume), '?')
        try:
            handle = _open(k32, f'\\\\.\\{drive}')
            try:
                out = ctypes.create_string_buffer(256)
                returned = ctypes.c_uint32()
                if k32.DeviceIoControl(handle, _IOCTL_DISK_GET_PARTITION_INFO_EX, None, 0, out, len(out),
                                       ctypes.byref(returned), None):
                    info.partition_style = _PARTITION_STYLES.get(int.from_bytes(out.raw[0:4], 'little'), '?')
                query = ctypes.create_string_buffer(12)            # StorageDeviceProperty, standard query
                out = ctypes.create_string_buffer(1024)
                if k32.DeviceIoControl(handle, _IOCTL_STORAGE_QUERY_PROPERTY, query, len(query), out, len(out),
                                       ctypes.byref(returned), None):
                    def text(offset_at: int) -> str:
                        offset = int.from_bytes(out.raw[offset_at:offset_at + 4], 'little')
                        return out.raw[offset:out.raw.index(b'\0', offset)].decode('ascii', 'replace').strip() if offset else ''
                    info.model = ' '.join(t for t in (text(12), text(16)) if t)
                    info.usb = int.from_bytes(out.raw[28:32], 'little') == _BUS_USB
            finally:
                k32.CloseHandle(handle)
        except OSError:
            pass
    if check_vcds and (root / 'POPS').is_dir():
        for vcd in sorted((root / 'POPS').glob('*.[vV][cC][dD]')):
            info.vcd_count += 1
            try:
                count = fragments(vcd)
            except OSError:
                continue
            if count > 1:
                info.fragmented[vcd.name] = count
    return info
