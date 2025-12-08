"""
Victor 9000 Disk Image Utility

A Python package for reading, writing, and manipulating Victor 9000
floppy and hard disk images with FAT12 and CP/M filesystem support.

Also supports IBM PC FAT12 floppy disk images.
"""

from .constants import (
    ATTR_ARCHIVE,
    ATTR_DIRECTORY,
    ATTR_HIDDEN,
    ATTR_READONLY,
    ATTR_SYSTEM,
    ATTR_VOLUME,
    CLUSTER_SIZE,
    DIR_ENTRY_SIZE,
    FAT_BAD,
    FAT_EOF_MAX,
    FAT_EOF_MIN,
    FAT_FREE,
    SECTOR_SIZE,
    SECTORS_PER_CLUSTER,
)
from .exceptions import (
    CorruptedDiskError,
    DirectoryFullError,
    DiskError,
    DiskFullError,
    FileNotFoundError,
    HardDiskLabelError,
    InvalidFilenameError,
    InvalidPartitionError,
    PartitionError,
    V9KError,
)
from .cpm import CPMFileInfo, V9KCPMDiskImage
from .floppy import IBMPCDiskImage, V9KDiskImage, V9KFloppyImage
from .formatter import OutputFormatter
from .harddisk import V9KHardDiskImage, V9KPartition
from .models import (
    CPMDirectoryEntry,
    DirectoryEntry,
    IBMPCBIOSParameterBlock,
    PhysicalDiskLabel,
    VirtualVolumeLabel,
)
from .utils import (
    detect_image_type,
    has_wildcards,
    match_entries,
    match_filename,
    parse_image_path,
    split_internal_path,
    validate_filename,
)
from .commands import cmd_attr, cmd_copy, cmd_delete, cmd_info, cmd_list

__version__ = "1.1.0"

__all__ = [
    # Main disk image classes
    "V9KDiskImage",
    "V9KFloppyImage",
    "IBMPCDiskImage",
    "V9KHardDiskImage",
    "V9KPartition",
    "V9KCPMDiskImage",
    # Data models
    "DirectoryEntry",
    "CPMDirectoryEntry",
    "CPMFileInfo",
    "PhysicalDiskLabel",
    "VirtualVolumeLabel",
    "IBMPCBIOSParameterBlock",
    # Exceptions
    "V9KError",
    "DiskError",
    "DiskFullError",
    "DirectoryFullError",
    "InvalidFilenameError",
    "FileNotFoundError",
    "CorruptedDiskError",
    "PartitionError",
    "InvalidPartitionError",
    "HardDiskLabelError",
    # Utilities
    "validate_filename",
    "parse_image_path",
    "detect_image_type",
    "split_internal_path",
    "has_wildcards",
    "match_filename",
    "match_entries",
    # Commands
    "cmd_attr",
    "cmd_info",
    "cmd_list",
    "cmd_copy",
    "cmd_delete",
    # Output
    "OutputFormatter",
    # Constants
    "SECTOR_SIZE",
    "DIR_ENTRY_SIZE",
    "SECTORS_PER_CLUSTER",
    "CLUSTER_SIZE",
    "FAT_FREE",
    "FAT_BAD",
    "FAT_EOF_MIN",
    "FAT_EOF_MAX",
    "ATTR_READONLY",
    "ATTR_HIDDEN",
    "ATTR_SYSTEM",
    "ATTR_VOLUME",
    "ATTR_DIRECTORY",
    "ATTR_ARCHIVE",
]
