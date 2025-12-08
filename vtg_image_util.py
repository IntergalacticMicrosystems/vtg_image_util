#!/usr/bin/env python3
"""
Victor 9000 Disk Image Utility

Copy files to/from and delete files on Victor 9000 disk images.
Supports FAT12 filesystem with subdirectories.
Supports both floppy and hard disk images with multiple partitions.

Usage:
    vtg_image_util.py list <image[:path]> [--json]           # List floppy
    vtg_image_util.py list <image>                            # List hard disk partitions
    vtg_image_util.py list <image:partition:path> [--json]    # List hard disk directory
    vtg_image_util.py copy <source> <dest> [--json]
    vtg_image_util.py delete <image:path> [--json]

This is a backwards-compatibility wrapper that imports from the vtg_image_util package.
"""

import sys

# Re-export everything from the package for backwards compatibility
from vtg_image_util import (
    # Main disk image classes
    V9KDiskImage,
    V9KFloppyImage,
    IBMPCDiskImage,
    V9KHardDiskImage,
    V9KPartition,
    V9KCPMDiskImage,
    # Data models
    DirectoryEntry,
    CPMDirectoryEntry,
    CPMFileInfo,
    PhysicalDiskLabel,
    VirtualVolumeLabel,
    IBMPCBIOSParameterBlock,
    # Exceptions
    V9KError,
    DiskError,
    DiskFullError,
    DirectoryFullError,
    InvalidFilenameError,
    FileNotFoundError,
    CorruptedDiskError,
    PartitionError,
    InvalidPartitionError,
    HardDiskLabelError,
    # Utilities
    validate_filename,
    parse_image_path,
    detect_image_type,
    split_internal_path,
    has_wildcards,
    match_filename,
    # Output
    OutputFormatter,
    # Constants
    SECTOR_SIZE,
    DIR_ENTRY_SIZE,
    SECTORS_PER_CLUSTER,
    CLUSTER_SIZE,
    FAT_FREE,
    FAT_BAD,
    FAT_EOF_MIN,
    FAT_EOF_MAX,
    ATTR_READONLY,
    ATTR_HIDDEN,
    ATTR_SYSTEM,
    ATTR_VOLUME,
    ATTR_DIRECTORY,
    ATTR_ARCHIVE,
)

# Import command functions
from vtg_image_util.commands import (
    cmd_list,
    cmd_copy,
    cmd_delete,
    copy_from_image,
    copy_to_image,
    print_extended_help,
    EXTENDED_HELP,
)

# Import the main function
from vtg_image_util.__main__ import main

# Also export match_entries for backwards compatibility
from vtg_image_util.utils import match_entries


if __name__ == '__main__':
    sys.exit(main())
