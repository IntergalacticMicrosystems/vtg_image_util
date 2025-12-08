"""
Disk image creation for Victor 9000 and IBM PC disk images.

Provides functions to create blank, formatted disk images.
"""

import struct
from typing import Literal

from .constants import (
    SECTOR_SIZE,
    SECTORS_PER_CLUSTER,
    FAT_EOF_MAX,
)
from .exceptions import DiskError


# Victor 9000 floppy disk parameters
V9K_FLOPPY_PARAMS = {
    'single': {
        'total_sectors': 1224,       # Single-sided
        'fat_start': 1,
        'fat_sectors': 1,
        'fat_copies': 2,
        'dir_start': 3,
        'dir_sectors': 8,
        'data_start': 11,
        'total_clusters': 1214,
        'flags': 0x00,               # Bit 0 = 0 for single-sided
    },
    'double': {
        'total_sectors': 2448,       # Double-sided
        'fat_start': 1,
        'fat_sectors': 2,
        'fat_copies': 2,
        'dir_start': 5,
        'dir_sectors': 8,
        'data_start': 13,
        'total_clusters': 2378,
        'flags': 0x01,               # Bit 0 = 1 for double-sided
    },
}

# IBM PC floppy disk parameters
IBM_FLOPPY_PARAMS = {
    '360K': {
        'total_sectors': 720,
        'sectors_per_track': 9,
        'heads': 2,
        'sectors_per_cluster': 2,
        'reserved_sectors': 1,
        'fat_copies': 2,
        'fat_sectors': 2,
        'root_entries': 112,
        'media_descriptor': 0xFD,
    },
    '720K': {
        'total_sectors': 1440,
        'sectors_per_track': 9,
        'heads': 2,
        'sectors_per_cluster': 2,
        'reserved_sectors': 1,
        'fat_copies': 2,
        'fat_sectors': 3,
        'root_entries': 112,
        'media_descriptor': 0xF9,
    },
    '1.2M': {
        'total_sectors': 2400,
        'sectors_per_track': 15,
        'heads': 2,
        'sectors_per_cluster': 1,
        'reserved_sectors': 1,
        'fat_copies': 2,
        'fat_sectors': 7,
        'root_entries': 224,
        'media_descriptor': 0xF9,
    },
    '1.44M': {
        'total_sectors': 2880,
        'sectors_per_track': 18,
        'heads': 2,
        'sectors_per_cluster': 1,
        'reserved_sectors': 1,
        'fat_copies': 2,
        'fat_sectors': 9,
        'root_entries': 224,
        'media_descriptor': 0xF0,
    },
}


def create_victor_floppy(
    path: str,
    sides: Literal['single', 'double'] = 'double',
    volume_label: str | None = None
) -> None:
    """
    Create a blank Victor 9000 floppy disk image.

    Args:
        path: Path for the new disk image file
        sides: 'single' for single-sided (~600KB) or 'double' for double-sided (~1.2MB)
        volume_label: Optional volume label (8 characters max)

    Raises:
        DiskError: If creation fails
    """
    if sides not in V9K_FLOPPY_PARAMS:
        raise DiskError(f"Invalid sides parameter: {sides}. Use 'single' or 'double'.")

    params = V9K_FLOPPY_PARAMS[sides]
    total_size = params['total_sectors'] * SECTOR_SIZE

    try:
        with open(path, 'wb') as f:
            # Create empty image
            f.write(bytes(total_size))
            f.seek(0)

            # Write boot sector
            boot_sector = _create_v9k_boot_sector(params)
            f.write(boot_sector)

            # Write FAT (both copies)
            fat = _create_fat12(params['total_clusters'])
            for copy in range(params['fat_copies']):
                f.seek((params['fat_start'] + copy * params['fat_sectors']) * SECTOR_SIZE)
                f.write(fat[:params['fat_sectors'] * SECTOR_SIZE])

            # Write root directory (already zeros, but add volume label if provided)
            if volume_label:
                f.seek(params['dir_start'] * SECTOR_SIZE)
                vol_entry = _create_volume_label_entry(volume_label)
                f.write(vol_entry)

    except OSError as e:
        raise DiskError(f"Failed to create disk image: {e}")


def create_ibm_floppy(
    path: str,
    format: Literal['360K', '720K', '1.2M', '1.44M'] = '1.44M',
    volume_label: str | None = None,
    oem_name: str = 'MSDOS5.0'
) -> None:
    """
    Create a blank IBM PC FAT12 floppy disk image.

    Args:
        path: Path for the new disk image file
        format: Disk format ('360K', '720K', '1.2M', or '1.44M')
        volume_label: Optional volume label (11 characters max)
        oem_name: OEM name for boot sector (8 characters)

    Raises:
        DiskError: If creation fails
    """
    if format not in IBM_FLOPPY_PARAMS:
        raise DiskError(f"Invalid format: {format}. Use '360K', '720K', '1.2M', or '1.44M'.")

    params = IBM_FLOPPY_PARAMS[format]
    total_size = params['total_sectors'] * SECTOR_SIZE

    # Calculate layout
    root_dir_sectors = (params['root_entries'] * 32 + SECTOR_SIZE - 1) // SECTOR_SIZE
    data_start = params['reserved_sectors'] + (params['fat_copies'] * params['fat_sectors']) + root_dir_sectors
    data_sectors = params['total_sectors'] - data_start
    total_clusters = data_sectors // params['sectors_per_cluster']

    try:
        with open(path, 'wb') as f:
            # Create empty image
            f.write(bytes(total_size))
            f.seek(0)

            # Write boot sector with BPB
            boot_sector = _create_ibm_boot_sector(params, oem_name)
            f.write(boot_sector)

            # Write FAT (both copies)
            fat = _create_fat12(total_clusters, params['media_descriptor'])
            fat_start = params['reserved_sectors']
            for copy in range(params['fat_copies']):
                f.seek((fat_start + copy * params['fat_sectors']) * SECTOR_SIZE)
                f.write(fat[:params['fat_sectors'] * SECTOR_SIZE])

            # Write root directory with volume label if provided
            root_dir_start = fat_start + (params['fat_copies'] * params['fat_sectors'])
            if volume_label:
                f.seek(root_dir_start * SECTOR_SIZE)
                vol_entry = _create_volume_label_entry(volume_label)
                f.write(vol_entry)

    except OSError as e:
        raise DiskError(f"Failed to create disk image: {e}")


def _create_v9k_boot_sector(params: dict) -> bytes:
    """Create a Victor 9000 boot sector."""
    boot = bytearray(SECTOR_SIZE)

    # Jump instruction (not bootable, but standard)
    boot[0:3] = b'\xEB\x3C\x90'  # JMP short + NOP

    # Victor-specific fields
    struct.pack_into('<H', boot, 26, SECTOR_SIZE)      # Sector size
    struct.pack_into('<H', boot, 28, params['data_start'])  # Data start sector
    struct.pack_into('<H', boot, 32, params['flags'])  # Flags (bit 0 = double-sided)
    boot[34] = 0x01  # Disc type

    return bytes(boot)


def _create_ibm_boot_sector(params: dict, oem_name: str) -> bytes:
    """Create an IBM PC FAT12 boot sector with BPB."""
    boot = bytearray(SECTOR_SIZE)

    # Jump instruction
    boot[0:3] = b'\xEB\x3C\x90'  # JMP short + NOP

    # OEM Name (8 bytes)
    oem = oem_name.encode('ascii')[:8].ljust(8)
    boot[0x03:0x0B] = oem

    # BPB (BIOS Parameter Block)
    struct.pack_into('<H', boot, 0x0B, SECTOR_SIZE)     # Bytes per sector
    boot[0x0D] = params['sectors_per_cluster']          # Sectors per cluster
    struct.pack_into('<H', boot, 0x0E, params['reserved_sectors'])  # Reserved sectors
    boot[0x10] = params['fat_copies']                   # Number of FATs
    struct.pack_into('<H', boot, 0x11, params['root_entries'])  # Root dir entries
    struct.pack_into('<H', boot, 0x13, params['total_sectors'])  # Total sectors (16-bit)
    boot[0x15] = params['media_descriptor']             # Media descriptor
    struct.pack_into('<H', boot, 0x16, params['fat_sectors'])  # Sectors per FAT
    struct.pack_into('<H', boot, 0x18, params['sectors_per_track'])  # Sectors per track
    struct.pack_into('<H', boot, 0x1A, params['heads'])  # Number of heads
    struct.pack_into('<I', boot, 0x1C, 0)               # Hidden sectors
    struct.pack_into('<I', boot, 0x20, 0)               # Total sectors (32-bit, 0 if 16-bit used)

    # Extended BPB (FAT12/16)
    boot[0x24] = 0x00                                   # Drive number
    boot[0x25] = 0x00                                   # Reserved
    boot[0x26] = 0x29                                   # Extended boot signature
    struct.pack_into('<I', boot, 0x27, 0x12345678)      # Volume serial number
    boot[0x2B:0x36] = b'NO NAME    '                    # Volume label (11 bytes)
    boot[0x36:0x3E] = b'FAT12   '                       # File system type (8 bytes)

    # Boot signature
    struct.pack_into('<H', boot, 0x1FE, 0xAA55)

    return bytes(boot)


def _create_fat12(total_clusters: int, media_descriptor: int = 0xF8) -> bytes:
    """
    Create an empty FAT12 table.

    The first two entries are reserved:
    - Entry 0: Media descriptor byte
    - Entry 1: End of chain marker
    """
    # Calculate FAT size in bytes (1.5 bytes per entry)
    fat_bytes = ((total_clusters + 2) * 3 + 1) // 2

    fat = bytearray(fat_bytes)

    # Entry 0: Media descriptor | 0xF00
    # Entry 1: 0xFFF (end of chain marker)
    # For FAT12, entries 0 and 1 are packed as:
    # Byte 0: media_descriptor
    # Byte 1: 0xFF
    # Byte 2: 0xFF
    fat[0] = media_descriptor
    fat[1] = 0xFF
    fat[2] = 0xFF

    return bytes(fat)


def _create_volume_label_entry(label: str) -> bytes:
    """Create a 32-byte directory entry for a volume label."""
    entry = bytearray(32)

    # Format label (11 characters, space-padded)
    label = label.upper()[:11].ljust(11)
    entry[0:11] = label.encode('ascii')

    # Attribute byte: volume label
    entry[11] = 0x08  # ATTR_VOLUME

    return bytes(entry)


def get_supported_formats() -> dict:
    """
    Get information about supported disk formats.

    Returns:
        Dictionary with format information
    """
    return {
        'victor_floppy': {
            'single': {
                'description': 'Victor 9000 single-sided floppy',
                'capacity': '~600 KB',
                'clusters': 1214,
            },
            'double': {
                'description': 'Victor 9000 double-sided floppy',
                'capacity': '~1.2 MB',
                'clusters': 2378,
            },
        },
        'ibm_floppy': {
            '360K': {
                'description': 'IBM PC 5.25" DD floppy',
                'capacity': '360 KB',
            },
            '720K': {
                'description': 'IBM PC 3.5" DD floppy',
                'capacity': '720 KB',
            },
            '1.2M': {
                'description': 'IBM PC 5.25" HD floppy',
                'capacity': '1.2 MB',
            },
            '1.44M': {
                'description': 'IBM PC 3.5" HD floppy',
                'capacity': '1.44 MB',
            },
        },
    }
