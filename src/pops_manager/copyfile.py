"""Exclusive file copy with progress. On Windows uses CopyFileExW: the destination size is reserved
up front (helps keep VCDs contiguous, which POPStarter needs) and large files bypass the cache."""
from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
import ctypes
import sys

Progress = Callable[[int, int], None]   # (bytes done in this file, file size)
_CHUNK = 8 * 1024 * 1024
_NO_BUFFERING_FROM = 64 * 1024 * 1024
_COPY_FILE_FAIL_IF_EXISTS = 0x1
_COPY_FILE_NO_BUFFERING = 0x1000
_PROGRESS_CONTINUE, _PROGRESS_CANCEL = 0, 1
_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS, _ERROR_REQUEST_ABORTED = 80, 183, 1235


def _python_copy(source: Path, dest: Path, progress: Progress | None) -> None:
    size = source.stat().st_size
    done = 0
    buffer = bytearray(_CHUNK)
    view = memoryview(buffer)
    with source.open('rb') as inp, dest.open('xb') as out:
        while n := inp.readinto(buffer):
            out.write(view[:n])
            done += n
            if progress:
                progress(done, size)


if sys.platform == 'win32':
    _ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong,
                                  ctypes.c_longlong, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                  ctypes.c_void_p, ctypes.c_void_p)
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _k32.CopyFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, _ROUTINE, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_uint32]
    _k32.CopyFileExW.restype = ctypes.c_int

    def _native_copy(source: Path, dest: Path, progress: Progress | None) -> None:
        failure: list[BaseException] = []

        @_ROUTINE
        def routine(total, transferred, _ss, _st, _sn, _reason, _hs, _hd, _data):
            try:
                if progress:
                    progress(transferred, total)
                return _PROGRESS_CONTINUE
            except BaseException as error:      # cannot cross the C boundary: stop and re-raise below
                failure.append(error)
                return _PROGRESS_CANCEL

        flags = _COPY_FILE_FAIL_IF_EXISTS
        if source.stat().st_size >= _NO_BUFFERING_FROM:
            flags |= _COPY_FILE_NO_BUFFERING
        if not _k32.CopyFileExW(str(source), str(dest), routine, None, None, flags):
            error = ctypes.get_last_error()
            if failure:
                raise failure[0]
            if error in (_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS):
                raise FileExistsError(f'Refusing to overwrite: {dest}')
            raise OSError(error, f'Copy failed: {source} -> {dest}: {ctypes.FormatError(error).strip()}')
        if failure:
            raise failure[0]
else:
    _native_copy = None


def copy_file(source: Path, dest: Path, progress: Progress | None = None) -> None:
    """Copies source to dest; fails if dest exists. Partial files are removed on failure."""
    if dest.exists():
        raise FileExistsError(f'Refusing to overwrite: {dest}')
    try:
        (_native_copy or _python_copy)(source, dest, progress)
    except FileExistsError:
        raise
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    if dest.stat().st_size != source.stat().st_size:
        dest.unlink(missing_ok=True)
        raise OSError(f'Incomplete copy: {dest}')
