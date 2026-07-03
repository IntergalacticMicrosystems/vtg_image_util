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
        'disk.chd:0:\\FILE.COM' -> ('disk.chd', 0, 'FILE.COM')
    """
    lower = path_spec.lower()

    # Find the split point: an image extension only counts when followed by
    # ':' or the end of the string, so directories like 'my.imgs\' or files
    # like 'backup.img.bak' are not mistaken for disk images.
    split_pos = None
    for ext in ['.img', '.ima', '.dsk', '.chd']:
        search_from = 0
        while True:
            idx = lower.find(ext, search_from)
            if idx == -1:
                break
            end = idx + len(ext)
            if end == len(path_spec) or path_spec[end] == ':':
                if split_pos is None or end < split_pos:
                    split_pos = end
                break
            search_from = idx + 1

    if split_pos is None:
        # Regular filesystem path (no recognized image extension)
        return (None, None, path_spec)

    image_path = path_spec[:split_pos]
    remainder = path_spec[split_pos:]

    if not remainder or remainder == ':':
        # Just the image path (e.g., 'disk.img' or 'disk.img:')
        return (image_path, None, None)

    remainder = remainder[1:]  # Skip the colon

    # A leading run of digits is a partition number only when followed by
    # ':' , '\', '/' or the end — 'disk.img:123.TXT' is a filename.
    if remainder[0].isdigit():
        num_end = 0
        while num_end < len(remainder) and remainder[num_end].isdigit():
            num_end += 1
        after_num = remainder[num_end:]

        if not after_num:
            # 'hd.img:0'
            return (image_path, int(remainder[:num_end]), None)
        if after_num.startswith(':'):
            # 'hd.img:0:' or 'hd.img:0:\path' — root is '' (not None)
            partition = int(remainder[:num_end])
            after_colon = after_num[1:]
            if not after_colon:
                return (image_path, partition, None)
            return (image_path, partition, after_colon.lstrip('\\/'))
        if after_num.startswith('\\') or after_num.startswith('/'):
            # 'hd.img:0\path'
            partition = int(remainder[:num_end])
            return (image_path, partition, after_num.lstrip('\\/'))
        # Digits followed by something else: a filename like '123.TXT'

    # No partition number — floppy format. 'disk.img:\' means root ('').
    if remainder.startswith('\\') or remainder.startswith('/'):
        return (image_path, None, remainder.lstrip('\\/'))
    return (image_path, None, remainder)


def detect_image_type(image_path: str) -> str:
    """
    Detect if image is 'floppy', 'harddisk', 'ibmpc', or 'cpm'.
    Uses file size and structure heuristics.
    CHD files are treated as hard disk images.
    """
    # Check for CHD format first (by signature)
    try:
        with open(image_path, 'rb') as f:
            sig = f.read(8)
            if sig == b'MComprHD':
                return 'harddisk'  # CHD is handled by V9KHardDiskImage
    except OSError:
        pass

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


def _wildcard_segment_regex(segment: str, any_char: str) -> str:
    """
    Convert one pattern segment (name or extension) to a regex fragment.
    '?' matches a single character but, like DOS, may also match nothing
    at the end of the segment.
    """
    regex = ''
    trailing_q = len(segment) - len(segment.rstrip('?'))
    body = segment[:len(segment) - trailing_q]
    for char in body:
        if char == '*':
            regex += any_char + '*'
        elif char == '?':
            regex += any_char
        elif char in '.^$+{}[]|()\\':
            regex += '\\' + char
        else:
            regex += char
    regex += (any_char + '?') * trailing_q
    return regex


def match_filename(pattern: str, filename: str) -> bool:
    """
    Match a DOS-style wildcard pattern against a filename.
    Supports * (any characters) and ? (single character; at the end of the
    name or extension it may also match nothing, as in DOS). Like DOS,
    '*.*' matches every file, including those without an extension.
    """
    pattern = pattern.upper()
    filename = filename.upper()

    if '.' in pattern:
        # Match name and extension separately (8.3 patterns have one dot)
        name_pat, ext_pat = pattern.rsplit('.', 1)
        regex = _wildcard_segment_regex(name_pat, '[^.]')
        if ext_pat == '':
            # 'NAME.' matches files WITHOUT an extension, as in DOS
            pass
        elif ext_pat == '*' or ext_pat == '?' * len(ext_pat):
            # '*.*' / 'NAME.*' also match files without an extension
            regex += '(\\.' + _wildcard_segment_regex(ext_pat, '[^.]') + ')?'
        else:
            regex += '\\.' + _wildcard_segment_regex(ext_pat, '[^.]')
    else:
        regex = _wildcard_segment_regex(pattern, '.')

    return bool(re.match('^' + regex + '$', filename))


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
