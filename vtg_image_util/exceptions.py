"""
Custom exceptions for Victor 9000 and IBM PC disk image utilities.
"""


class V9KError(Exception):
    """Base exception for all V9K disk errors."""
    pass


class DiskError(V9KError):
    """Error reading/writing disk image."""
    pass


class DiskFullError(V9KError):
    """Not enough free space on disk."""
    pass


class DirectoryFullError(V9KError):
    """No free directory entries available."""
    pass


class InvalidFilenameError(V9KError):
    """Filename does not conform to 8.3 format."""
    pass


class FileNotFoundError(V9KError):
    """File not found in disk image."""
    pass


class CorruptedDiskError(V9KError):
    """Disk structure is corrupted."""
    pass


class PartitionError(V9KError):
    """Error related to partition operations."""
    pass


class InvalidPartitionError(PartitionError):
    """Partition index out of range or invalid."""
    pass


class HardDiskLabelError(V9KError):
    """Error parsing hard disk label structure."""
    pass
