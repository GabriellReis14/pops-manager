import hashlib
from pathlib import Path
import pytest
from pops_manager import diagnostics, vmc

# MD5 of the SLOT0/SLOT1.VMC written by "VMC and MultiDisc Creator" v1.0 (observed).
ORIGINAL_VMC_MD5 = 'd8f29ffd55cb1e4f77987a1e07472d66'


def test_blank_vmc_identical_to_original_tool():
    card = vmc.blank_vmc()
    assert len(card) == 128 * 1024
    assert hashlib.md5(card).hexdigest() == ORIGINAL_VMC_MD5


def test_blank_vmc_frame_checksums():
    card = vmc.blank_vmc()
    for frame in range(64):
        data = card[frame * 128:(frame + 1) * 128]
        checksum = 0
        for byte in data[:127]:
            checksum ^= byte
        if any(data):
            assert data[127] == checksum, frame
    assert card[:2] == b'MC'


def test_multidisc_helpers():
    groups = vmc.multidisc_groups(['D2_Fin_Fan_VII', 'Crash', 'D1_Fin_Fan_VII', 'D1_Met_Gea_Sol'])
    assert groups == {'fin_fan_vii': ['D1_Fin_Fan_VII', 'D2_Fin_Fan_VII'], 'met_gea_sol': ['D1_Met_Gea_Sol']}
    assert vmc.discs_txt(['D1_X', 'D2_X']) == 'D1_X.VCD\r\nD2_X.VCD\r\n'
    assert vmc.vmcdir_txt(['D1_X', 'D2_X']) == 'D1_X'
    assert vmc.disc_info('D12_Long_Name') == (12, 'Long_Name') and vmc.disc_info('Crash') is None


@pytest.mark.skipif(not diagnostics.IS_WINDOWS, reason='Windows only')
def test_fragments_and_device_info(tmp_path):
    small = tmp_path / 'a.bin'; small.write_bytes(b'x' * 100_000)
    assert diagnostics.fragments(small) >= 1
    empty = tmp_path / 'empty.bin'; empty.write_bytes(b'')
    assert diagnostics.fragments(empty) == 1
    (tmp_path / 'POPS').mkdir(); (tmp_path / 'POPS' / 'G.VCD').write_bytes(b'v' * 10_000)
    info = diagnostics.device_info(tmp_path)
    assert info.filesystem != '?' and info.cluster_size > 0 and info.vcd_count == 1
    assert info.partition_style in ('MBR', 'GPT', 'RAW', '?')


@pytest.mark.parametrize('fs, style, sector, frag, codes', [
    ('FAT32', 'MBR', 512, {}, []),
    ('exFAT', 'MBR', 512, {}, []),
    ('NTFS', 'MBR', 512, {}, ['fs_unsupported']),
    ('FAT32', 'GPT', 4096, {'A.VCD': 3}, ['gpt', 'sector_size', 'fragmented']),
])
def test_device_warnings(fs, style, sector, frag, codes):
    info = diagnostics.DeviceInfo(Path('X:/'), filesystem=fs, partition_style=style, sector_size=sector, fragmented=frag)
    assert info.warnings() == codes


@pytest.mark.parametrize('model, nvme', [('Realtek RTL9210 NVME', True), ('JMicron Tech', False), ('SanDisk Cruzer Blade', False), ('ASMT ASM2362', True)])
def test_nvme_bridge_warning(model, nvme):
    info = diagnostics.DeviceInfo(Path('X:/'), filesystem='FAT32', partition_style='MBR', sector_size=512, model=model)
    assert ('nvme_bridge' in info.warnings()) is nvme
