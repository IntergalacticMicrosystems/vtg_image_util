"""
Floppy disk image classes for Victor 9000 and IBM PC.
"""

import struct
from typing import BinaryIO

from .constants import (
    CLUSTER_SIZE,
    SECTOR_SIZE,
    SECTORS_PER_CLUSTER,
)
from .exceptions import DiskError
from .fat12 import DiskImageFileMixin, FAT12Base
from .models import IBMPCBIOSParameterBlock, DirectoryEntry
from .utils import has_wildcards, match_filename


class V9KDiskImage(DiskImageFileMixin, FAT12Base):
    """Victor 9000 floppy disk image operations."""

    def __init__(self, image_path: str, readonly: bool = True):
        """Open disk image and read boot sector parameters."""
        # Initialize file handle
        self._file: BinaryIO | None = None
        self._open_file(image_path, readonly)

        # Disk geometry (set by _read_boot_sector)
        self._sector_size = SECTOR_SIZE
        self._double_sided = False
        self._disc_type = 0
        self._data_start = 0
        self._fat_start = 1
        self._fat_sectors = 1
        self._dir_start = 0
        self._dir_sectors = 8
        self._total_clusters = 0

        # Parse boot sector
        self._read_boot_sector()

        # Initialize base class and load FAT
        FAT12Base.__init__(self)
        self._load_fat()

    def _read_boot_sector(self) -> None:
        """Parse boot sector to determine disk geometry."""
        boot = self.read_sector(0)

        # Sector size at offset 26-27
        self._sector_size = struct.unpack_from('<H', boot, 26)[0]
        if self._sector_size != 512:
            self._sector_size = 512

        # Flags at offset 32-33
        flags = struct.unpack_from('<H', boot, 32)[0]
        self._double_sided = bool(flags & 0x01)

        # Disc type at offset 34
        self._disc_type = boot[34]

        # Data start at offset 28-29
        self._data_start = struct.unpack_from('<H', boot, 28)[0]

        # Set geometry based on single/double sided
        if self._double_sided:
            self._fat_start = 1
            self._fat_sectors = 2
            self._dir_start = 5
            self._dir_sectors = 8
            if self._data_start == 0:
                self._data_start = 13
            self._total_clusters = 2378
        else:
            self._fat_start = 1
            self._fat_sectors = 1
            self._dir_start = 3
            self._dir_sectors = 8
            if self._data_start == 0:
                self._data_start = 11
            self._total_clusters = 1214

    # =========================================================================
    # Abstract Properties Implementation
    # =========================================================================

    @property
    def fat_start(self) -> int:
        return self._fat_start

    @property
    def fat_sectors(self) -> int:
        return self._fat_sectors

    @property
    def num_fat_copies(self) -> int:
        return 2  # Victor always uses 2 FAT copies

    @property
    def dir_start(self) -> int:
        return self._dir_start

    @property
    def dir_sectors(self) -> int:
        return self._dir_sectors

    @property
    def data_start(self) -> int:
        return self._data_start

    @property
    def total_clusters(self) -> int:
        return self._total_clusters

    @property
    def sectors_per_cluster(self) -> int:
        return SECTORS_PER_CLUSTER  # Always 4 for Victor floppy

    @property
    def cluster_size(self) -> int:
        return CLUSTER_SIZE  # Always 2048 for Victor floppy

    # =========================================================================
    # V9K-specific Methods
    # =========================================================================

    def list_files_recursive(
        self,
        path_components: list[str] | None = None,
        pattern: str | None = None
    ) -> list[tuple[str, DirectoryEntry]]:
        """
        Recursively list files in a directory tree.
        Returns list of (path, entry) tuples where path is the relative path.
        If pattern is provided, only matching files are returned.
        """
        results = []

        def recurse(dir_cluster: int | None, current_path: str):
            entries = self.read_directory(dir_cluster)
            for entry in entries:
                if entry.is_dot_entry:
                    continue

                entry_path = current_path + '\\' + entry.full_name if current_path else entry.full_name

                if entry.is_directory:
                    recurse(entry.first_cluster, entry_path)
                else:
                    if pattern is None or match_filename(pattern, entry.full_name):
                        results.append((entry_path, entry))

        # Determine starting directory
        if path_components:
            if has_wildcards(path_components[-1]):
                if len(path_components) > 1:
                    dir_cluster, _ = self.resolve_path(path_components[:-1])
                else:
                    dir_cluster = None
                file_pattern = path_components[-1]
            else:
                try:
                    dir_cluster, entry = self.resolve_path(path_components)
                    if entry is not None and not entry.is_directory:
                        return [('\\'.join(path_components), entry)]
                    file_pattern = None
                except Exception:
                    if len(path_components) > 1:
                        dir_cluster, _ = self.resolve_path(path_components[:-1])
                    else:
                        dir_cluster = None
                    file_pattern = path_components[-1]
        else:
            dir_cluster = None
            file_pattern = pattern

        # For non-recursive wildcard, just list matching files
        if file_pattern and not pattern:
            entries = self.read_directory(dir_cluster)
            base_path = '\\'.join(path_components[:-1]) if path_components and len(path_components) > 1 else ''
            for entry in entries:
                if entry.is_dot_entry:
                    continue
                if match_filename(file_pattern, entry.full_name):
                    entry_path = base_path + '\\' + entry.full_name if base_path else entry.full_name
                    results.append((entry_path, entry))
            return results

        # Recursive listing
        base_path = '\\'.join(path_components) if path_components and not has_wildcards(path_components[-1]) else ''
        recurse(dir_cluster, base_path)
        return results


# Alias for backward compatibility
V9KFloppyImage = V9KDiskImage


class IBMPCDiskImage(DiskImageFileMixin, FAT12Base):
    """IBM PC FAT12 floppy disk image operations."""

    def __init__(self, image_path: str, readonly: bool = True):
        """Open disk image and read BPB parameters."""
        # Initialize file handle
        self._file: BinaryIO | None = None
        self._bpb: IBMPCBIOSParameterBlock | None = None
        self._open_file(image_path, readonly)

        # Parse BPB
        self._read_bpb()

        # Initialize base class and load FAT
        FAT12Base.__init__(self)
        self._load_fat()

    def _read_bpb(self) -> None:
        """Parse BPB from boot sector."""
        boot = self.read_sector(0)
        self._bpb = IBMPCBIOSParameterBlock.from_bytes(boot)

    # =========================================================================
    # Abstract Properties Implementation - delegate to BPB
    # =========================================================================

    @property
    def fat_start(self) -> int:
        return self._bpb.fat_start

    @property
    def fat_sectors(self) -> int:
        return self._bpb.fat_sectors

    @property
    def num_fat_copies(self) -> int:
        return self._bpb.num_fats

    @property
    def dir_start(self) -> int:
        return self._bpb.root_dir_start

    @property
    def dir_sectors(self) -> int:
        return self._bpb.root_dir_sectors

    @property
    def data_start(self) -> int:
        return self._bpb.data_start

    @property
    def total_clusters(self) -> int:
        return self._bpb.total_clusters

    @property
    def sectors_per_cluster(self) -> int:
        return self._bpb.sectors_per_cluster

    @property
    def cluster_size(self) -> int:
        return self._bpb.cluster_size
