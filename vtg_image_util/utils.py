"""
Utility functions for Victor 9000 and IBM PC disk image utilities.
"""

import os
import re
import struct

from .constants import (
    CPM_DIR_START_SECTOR,
    PDL_DEVICE_ID,
    PDL_LABEL_TYPE,
    SECTOR_SIZE,
    VALID_FILENAME_CHARS,
)
from .exceptions import InvalidFilenameError
from .models import DirectoryEntry


def validate_filename(filename: str) -> tuple[str, str]:
    """
    Validate and parse 8.3 filename.
    Returns (name, extension) both uppercase and space-padded.
    Raises InvalidFilenameError if not valid 8.3 format.
    """
    filename = filename.upper().strip()

    if not filename:
        raise InvalidFilenameError("Filename cannot be empty")

    # Split name and extension
    if '.' in filename:
        parts = filename.rsplit('.', 1)
        name = parts[0]
        ext = parts[1] if len(parts) > 1 else ''
    else:
        name = filename
        ext = ''

    # Validate lengths
    if len(name) > 8:
        raise InvalidFilenameError(f"Filename '{name}' exceeds 8 characters")
    if len(ext) > 3:
        raise InvalidFilenameError(f"Extension '{ext}' exceeds 3 characters")
    if len(name) == 0:
        raise InvalidFilenameError("Filename cannot be empty")

    # Validate characters
    for char in name:
        if char not in VALID_FILENAME_CHARS:
            raise InvalidFilenameError(f"Invalid character '{char}' in filename")
    for char in ext:
        if char not in VALID_FILENAME_CHARS:
            raise InvalidFilenameError(f"Invalid character '{char}' in extension")

    # Pad with spaces
    name = name.ljust(8)
    ext = ext.ljust(3)

    return name, ext


def parse_image_path(path_spec: str) -> tuple[str | None, int | None, str | None]:
    """
    Parse path into (image_path, partition, internal_path).

    For floppies: partition is None
    For hard disks: partition is integer 0-N

    Examples:
        'disk.img:\\FILE.COM' -> ('disk.img', None, 'FILE.COM')
        'hd.img:0:\\FILE.COM' -> ('hd.img', 0, 'FILE.COM')
        'hd.img:1:\\DIR\\F.TXT' -> ('hd.img', 1, 'DIR\\F.TXT')
        'hd.img:0:' -> ('hd.img', 0, None)
        'hd.img' -> ('hd.img', None, None)
    """
    lower = path_spec.lower()

    # Find image file extensions
    for ext in ['.img', '.ima', '.dsk']:
        idx = lower.find(ext)
        if idx != -1:
            split_pos = idx + len(ext)
            image_path = path_spec[:split_pos]
            remainder = path_spec[split_pos:]

            if not remainder:
                # Just the image path (e.g., 'disk.img')
                return (image_path, None, None)

            if remainder.startswith(':'):
                remainder = remainder[1:]  # Skip first colon

                if not remainder:
                    # Just 'disk.img:'
                    return (image_path, None, None)

                # Check if next part is a partition number
                if remainder[0].isdigit():
                    # Find where partition number ends
                    num_end = 0
                    while num_end < len(remainder) and remainder[num_end].isdigit():
                        num_end += 1
                    partition = int(remainder[:num_end])
                    after_num = remainder[num_end:]

                    if not after_num:
                        # 'hd.img:0'
                        return (image_path, partition, None)
                    elif after_num.startswith(':'):
                        # 'hd.img:0:' or 'hd.img:0:\path'
                        after_colon = after_num[1:]
                        if not after_colon:
                            return (image_path, partition, None)
                        elif after_colon.startswith('\\') or after_colon.startswith('/'):
                            return (image_path, partition, after_colon[1:] if after_colon else None)
                        else:
                            return (image_path, partition, after_colon)
                    elif after_num.startswith('\\') or after_num.startswith('/'):
                        # 'hd.img:0\path' - partition with backslash
                        return (image_path, partition, after_num[1:] if len(after_num) > 1 else None)
                    else:
                        # Invalid format
                        return (None, None, path_spec)

                # No partition number - floppy format
                if remainder.startswith('\\') or remainder.startswith('/'):
                    return (image_path, None, remainder[1:] if len(remainder) > 1 else None)
                else:
                    return (image_path, None, remainder)

            # Extension found but no colon after - just image path
            return (image_path, None, None)

    # Regular filesystem path (no recognized image extension)
    return (None, None, path_spec)


def detect_image_type(image_path: str) -> str:
    """
    Detect if image is 'floppy', 'harddisk', 'ibmpc', or 'cpm'.
    Uses file size and structure heuristics.
    """
    try:
        file_size = os.path.getsize(image_path)
    except OSError:
        return 'floppy'  # Default to Victor floppy on error

    # Size heuristic: floppies are ~600KB-1.44MB, hard disks are larger
    if file_size > 2 * 1024 * 1024:  # > 2MB likely hard disk
        return 'harddisk'

    # Read sector 0 for detection
    try:
        with open(image_path, 'rb') as f:
            sector0 = f.read(512)

        if len(sector0) < 512:
            return 'floppy'

        # Check for IBM PC FAT12 signatures
        # 1. Boot signature 0x55AA at offset 0x1FE
        boot_sig = struct.unpack_from('<H', sector0, 0x1FE)[0]

        # 2. First byte is jump instruction (0xEB or 0xE9)
        is_jump = sector0[0] in (0xEB, 0xE9)

        # 3. Valid BPB fields
        bytes_per_sector = struct.unpack_from('<H', sector0, 0x0B)[0]
        sectors_per_cluster = sector0[0x0D]
        reserved_sectors = struct.unpack_from('<H', sector0, 0x0E)[0]
        num_fats = sector0[0x10]
        media_descriptor = sector0[0x15]

        # IBM PC detection criteria
        if (boot_sig == 0xAA55 and
            is_jump and
            bytes_per_sector == 512 and
            sectors_per_cluster in (1, 2, 4, 8) and
            reserved_sectors >= 1 and
            num_fats in (1, 2) and
            media_descriptor >= 0xF0):
            return 'ibmpc'

        # Check for Victor hard disk label structure
        label_type = struct.unpack_from('<H', sector0, PDL_LABEL_TYPE)[0]
        device_id = struct.unpack_from('<H', sector0, PDL_DEVICE_ID)[0]

        # Hard disk label has label_type=1 and device_id=1
        if label_type == 0x0001 and device_id == 0x0001:
            return 'harddisk'

        # Check for CP/M disk by examining directory structure
        # Victor 9000 CP/M boot sector often starts with 0xFF or 0xE5
        if sector0[0] in (0xFF, 0xE5, 0x00) and _is_cpm_disk(image_path):
            return 'cpm'

    except OSError:
        pass

    return 'floppy'  # Default to Victor floppy


def _check_cpm_dir_at_sector(data: bytes, sector: int) -> int:
    """Check if valid CP/M directory exists at given sector. Returns count of valid entries."""
    offset = sector * SECTOR_SIZE
    if offset + SECTOR_SIZE > len(data):
        return 0

    valid_entries = 0
    for i in range(4):  # Check first 4 entries
        entry = data[offset + i * 32:offset + (i + 1) * 32]
        if len(entry) < 32:
            break

        user = entry[0]
        # Valid user number (0-15) or deleted (0xE5)
        if user > 15 and user != 0xE5:
            continue

        # Check filename is printable ASCII (with high bit masked)
        name_bytes = entry[1:9]
        try:
            name = bytes([b & 0x7F for b in name_bytes]).decode('ascii')
            # Should be mostly printable or space
            if all(32 <= ord(c) < 127 for c in name):
                valid_entries += 1
        except (UnicodeDecodeError, ValueError):
            continue

    return valid_entries


def detect_cpm_dir_sector(image_path: str) -> int | None:
    """Detect the directory start sector for a CP/M disk image.

    Returns the sector number (76 or 94) or None if not a valid CP/M disk.
    """
    try:
        with open(image_path, 'rb') as f:
            data = f.read()

        # Check possible directory locations
        # Victor CP/M disks use sector 76, 94, or occasionally sector 1
        for sector in [76, 94, 1]:
            if _check_cpm_dir_at_sector(data, sector) >= 2:
                return sector

        return None
    except OSError:
        return None


def _is_cpm_disk(image_path: str) -> bool:
    """Check if disk has valid CP/M directory structure."""
    return detect_cpm_dir_sector(image_path) is not None


def split_internal_path(internal_path: str) -> list[str]:
    """Split internal path into components."""
    if not internal_path:
        return []
    # Remove leading backslash if present
    path = internal_path.lstrip('\\/')
    if not path:
        return []
    # Split on backslash or forward slash
    parts = []
    for part in path.replace('/', '\\').split('\\'):
        if part:
            parts.append(part.upper())
    return parts


def has_wildcards(pattern: str) -> bool:
    """Check if a string contains wildcard characters."""
    return '*' in pattern or '?' in pattern


def match_filename(pattern: str, filename: str) -> bool:
    """
    Match a DOS-style wildcard pattern against a filename.
    Supports * (any characters) and ? (single character).
    """
    pattern = pattern.upper()
    filename = filename.upper()

    # Convert DOS wildcard pattern to regex
    # * matches any characters, ? matches single character
    regex = ''
    for char in pattern:
        if char == '*':
            regex += '.*'
        elif char == '?':
            regex += '.'
        elif char in '.^$+{}[]|()\\':
            regex += '\\' + char
        else:
            regex += char

    # Anchor the pattern
    regex = '^' + regex + '$'

    return bool(re.match(regex, filename))


def match_entries(entries: list[DirectoryEntry], pattern: str) -> list[DirectoryEntry]:
    """
    Filter directory entries by wildcard pattern.
    Returns entries whose full_name matches the pattern.
    """
    if not has_wildcards(pattern):
        # No wildcards - exact match
        pattern_upper = pattern.upper()
        return [e for e in entries if e.full_name.upper() == pattern_upper]

    return [e for e in entries if match_filename(pattern, e.full_name)]
