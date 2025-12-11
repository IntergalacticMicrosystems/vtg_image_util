"""
FAT12 filesystem base class for Victor 9000 and IBM PC disk images.

This module provides the abstract base class for FAT12 operations that is
shared between V9KDiskImage, IBMPCDiskImage, and V9KPartition.
"""

import time
from abc import ABC, abstractmethod
from typing import BinaryIO

from .constants import (
    ATTR_ARCHIVE,
    ATTR_DIRECTORY,
    ATTR_HIDDEN,
    ATTR_READONLY,
    ATTR_SYSTEM,
    DIR_ENTRY_SIZE,
    FAT_FREE,
    SECTOR_SIZE,
)
from .exceptions import (
    CorruptedDiskError,
    DirectoryFullError,
    DiskError,
    DiskFullError,
    FileNotFoundError,
    InvalidFilenameError,
)
from .models import DirectoryEntry
from .utils import has_wildcards, match_filename, validate_filename


class FAT12Base(ABC):
    """
    Abstract base class for FAT12 filesystem operations.

    Subclasses must implement:
    - Sector I/O: read_sector(), write_sector()
    - Geometry properties: fat_start, fat_sectors, num_fat_copies,
                          dir_start, dir_sectors, data_start,
                          total_clusters, sectors_per_cluster, cluster_size
    - Initialization: __init__ must call _load_fat() after setting geometry
    """

    def __init__(self):
        """Base initializer - subclasses call after setting geometry."""
        self._fat_data: bytearray | None = None
        self._fat_dirty: bool = False
        # Don't overwrite readonly if already set by mixin
        if not hasattr(self, 'readonly'):
            self.readonly: bool = True

    # =========================================================================
    # Abstract Properties - Must be implemented by subclasses
    # =========================================================================

    @property
    @abstractmethod
    def fat_start(self) -> int:
        """First sector of FAT."""
        pass

    @property
    @abstractmethod
    def fat_sectors(self) -> int:
        """Number of sectors in one FAT copy."""
        pass

    @property
    @abstractmethod
    def num_fat_copies(self) -> int:
        """Number of FAT copies (typically 2)."""
        pass

    @property
    @abstractmethod
    def dir_start(self) -> int:
        """First sector of root directory."""
        pass

    @property
    @abstractmethod
    def dir_sectors(self) -> int:
        """Number of sectors in root directory."""
        pass

    @property
    @abstractmethod
    def data_start(self) -> int:
        """First sector of data area."""
        pass

    @property
    @abstractmethod
    def total_clusters(self) -> int:
        """Total number of data clusters."""
        pass

    @property
    @abstractmethod
    def sectors_per_cluster(self) -> int:
        """Sectors per cluster."""
        pass

    @property
    @abstractmethod
    def cluster_size(self) -> int:
        """Bytes per cluster."""
        pass

    # =========================================================================
    # Abstract Methods - Must be implemented by subclasses
    # =========================================================================

    @abstractmethod
    def read_sector(self, sector_num: int) -> bytes:
        """Read a single 512-byte sector."""
        pass

    @abstractmethod
    def write_sector(self, sector_num: int, data: bytes) -> None:
        """Write a single 512-byte sector."""
        pass

    # =========================================================================
    # Concrete Methods - Shared Implementation
    # =========================================================================

    def _cluster_to_sector(self, cluster: int) -> int:
        """Convert cluster number to first sector of that cluster."""
        return self.data_start + (cluster - 2) * self.sectors_per_cluster

    def _load_fat(self) -> None:
        """Load FAT into memory. Call after geometry is set."""
        fat_data = bytearray()
        for i in range(self.fat_sectors):
            sector = self.read_sector(self.fat_start + i)
            fat_data.extend(sector)
        self._fat_data = fat_data
        self._fat_dirty = False

    def _write_fat(self) -> None:
        """Write FAT back to disk (all copies)."""
        if self._fat_data is None or not self._fat_dirty:
            return

        for copy in range(self.num_fat_copies):
            copy_start = self.fat_start + (copy * self.fat_sectors)
            for i in range(self.fat_sectors):
                start = i * SECTOR_SIZE
                end = start + SECTOR_SIZE
                self.write_sector(copy_start + i, bytes(self._fat_data[start:end]))

        self._fat_dirty = False

    def get_fat_entry(self, cluster: int) -> int:
        """Read a 12-bit FAT entry."""
        if self._fat_data is None:
            raise DiskError("FAT not loaded")

        offset = cluster + (cluster // 2)  # 1.5 bytes per entry

        if offset + 1 >= len(self._fat_data):
            return FAT_FREE

        # Read 2 bytes at offset (little-endian)
        word = self._fat_data[offset] | (self._fat_data[offset + 1] << 8)

        if cluster % 2 == 0:
            # Even cluster: use lower 12 bits
            return word & 0x0FFF
        else:
            # Odd cluster: use upper 12 bits
            return word >> 4

    def set_fat_entry(self, cluster: int, value: int) -> None:
        """Write a 12-bit FAT entry."""
        if self._fat_data is None:
            raise DiskError("FAT not loaded")

        offset = cluster + (cluster // 2)

        if offset + 1 >= len(self._fat_data):
            raise DiskError(f"FAT offset out of range: {offset}")

        # Read existing 2 bytes
        word = self._fat_data[offset] | (self._fat_data[offset + 1] << 8)

        if cluster % 2 == 0:
            # Even: preserve upper 4 bits, set lower 12
            word = (word & 0xF000) | (value & 0x0FFF)
        else:
            # Odd: preserve lower 4 bits, set upper 12
            word = (word & 0x000F) | ((value & 0x0FFF) << 4)

        # Write back
        self._fat_data[offset] = word & 0xFF
        self._fat_data[offset + 1] = (word >> 8) & 0xFF

        self._fat_dirty = True

    def follow_chain(self, start_cluster: int) -> list[int]:
        """Return list of all clusters in chain starting at start_cluster."""
        if start_cluster == 0:
            return []

        chain = []
        cluster = start_cluster
        seen = set()

        while 0x002 <= cluster <= 0xFEF:
            if cluster in seen:
                raise CorruptedDiskError(f"Circular cluster chain at {cluster}")
            seen.add(cluster)
            chain.append(cluster)
            cluster = self.get_fat_entry(cluster)

        return chain

    def find_free_cluster(self) -> int | None:
        """Find a free cluster. Returns None if disk is full."""
        for cluster in range(2, self.total_clusters + 2):
            if self.get_fat_entry(cluster) == FAT_FREE:
                return cluster
        return None

    def allocate_chain(self, num_clusters: int) -> list[int]:
        """Allocate a chain of free clusters."""
        if num_clusters == 0:
            return []

        free_clusters = []
        for cluster in range(2, self.total_clusters + 2):
            if self.get_fat_entry(cluster) == FAT_FREE:
                free_clusters.append(cluster)
                if len(free_clusters) == num_clusters:
                    break

        if len(free_clusters) < num_clusters:
            raise DiskFullError(f"Need {num_clusters} clusters, only {len(free_clusters)} free")

        # Link clusters together
        for i, cluster in enumerate(free_clusters[:-1]):
            self.set_fat_entry(cluster, free_clusters[i + 1])

        # Mark last cluster as EOF
        self.set_fat_entry(free_clusters[-1], 0xFFF)

        return free_clusters

    def free_chain(self, start_cluster: int) -> None:
        """Free all clusters in a chain."""
        clusters = self.follow_chain(start_cluster)
        for cluster in clusters:
            self.set_fat_entry(cluster, FAT_FREE)

    def read_root_directory(self) -> list[DirectoryEntry]:
        """Read all entries from root directory."""
        entries = []
        for i in range(self.dir_sectors):
            sector_data = self.read_sector(self.dir_start + i)
            for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                offset = j * DIR_ENTRY_SIZE
                entry_data = sector_data[offset:offset + DIR_ENTRY_SIZE]
                entry = DirectoryEntry.from_bytes(entry_data)

                if entry.is_end:
                    return entries
                if not entry.is_free and not entry.is_volume_label:
                    entries.append(entry)

        return entries

    def read_subdirectory(self, start_cluster: int) -> list[DirectoryEntry]:
        """Read all entries from a subdirectory."""
        entries = []
        clusters = self.follow_chain(start_cluster)

        for cluster in clusters:
            first_sector = self._cluster_to_sector(cluster)
            for sec_offset in range(self.sectors_per_cluster):
                sector_data = self.read_sector(first_sector + sec_offset)

                for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                    offset = j * DIR_ENTRY_SIZE
                    entry_data = sector_data[offset:offset + DIR_ENTRY_SIZE]
                    entry = DirectoryEntry.from_bytes(entry_data)

                    if entry.is_end:
                        return entries
                    if not entry.is_free and not entry.is_volume_label:
                        entries.append(entry)

        return entries

    def read_directory(self, cluster: int | None = None) -> list[DirectoryEntry]:
        """Read directory entries. cluster=None for root directory."""
        if cluster is None:
            return self.read_root_directory()
        return self.read_subdirectory(cluster)

    def resolve_path(self, path_components: list[str]) -> tuple[int | None, DirectoryEntry | None]:
        """
        Resolve path to directory cluster and final entry.
        Returns (directory_cluster, entry) where:
        - directory_cluster is None for root directory
        - entry is None if path refers to a directory (not a file)
        - entry is the file entry if path refers to a file
        """
        if not path_components:
            return (None, None)  # Root directory

        current_cluster: int | None = None  # Start at root

        for i, component in enumerate(path_components):
            is_last = (i == len(path_components) - 1)

            # Validate component name
            name, ext = validate_filename(component)

            # Search current directory
            entries = self.read_directory(current_cluster)
            found = None

            for entry in entries:
                if entry.name == name and entry.extension == ext:
                    found = entry
                    break

            if found is None:
                raise FileNotFoundError(f"'{component}' not found")

            if is_last:
                # This is the target
                if found.is_directory:
                    return (found.first_cluster, None)
                else:
                    return (current_cluster, found)
            else:
                # Must be a directory to continue
                if not found.is_directory:
                    raise FileNotFoundError(f"'{component}' is not a directory")
                current_cluster = found.first_cluster

        return (current_cluster, None)

    def find_entry(self, path_components: list[str]) -> DirectoryEntry:
        """Find a file or directory entry by path."""
        if not path_components:
            raise FileNotFoundError("Empty path")

        dir_cluster, entry = self.resolve_path(path_components)

        if entry is not None:
            return entry

        # Path refers to a directory - return a synthetic entry for it
        dir_entries = self.read_directory(dir_cluster)
        # Find the "." entry which refers to self
        for e in dir_entries:
            if e.name.rstrip() == '.':
                return e

        # If no "." entry, create a synthetic one
        return DirectoryEntry(
            name='        ',
            extension='   ',
            attributes=ATTR_DIRECTORY,
            first_cluster=dir_cluster or 0,
            file_size=0
        )

    def read_file(self, path_components: list[str]) -> bytes:
        """Read complete file contents."""
        _, entry = self.resolve_path(path_components)

        if entry is None:
            raise FileNotFoundError("Path refers to a directory, not a file")

        if entry.is_directory:
            raise FileNotFoundError(f"'{entry.full_name}' is a directory")

        if entry.file_size == 0:
            return b''

        clusters = self.follow_chain(entry.first_cluster)
        data = bytearray()

        for cluster in clusters:
            first_sector = self._cluster_to_sector(cluster)
            for sec_offset in range(self.sectors_per_cluster):
                data.extend(self.read_sector(first_sector + sec_offset))

        # Truncate to actual file size
        return bytes(data[:entry.file_size])

    def _find_free_dir_slot(self, dir_cluster: int | None) -> tuple[int, int]:
        """
        Find a free directory entry slot.
        Returns (sector_num, entry_index) for root directory, or
        (cluster, entry_index) for subdirectory.
        """
        if dir_cluster is None:
            # Root directory - fixed size
            for i in range(self.dir_sectors):
                sector_data = self.read_sector(self.dir_start + i)
                for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                    offset = j * DIR_ENTRY_SIZE
                    first_byte = sector_data[offset]
                    if first_byte == 0x00 or first_byte == 0xE5:
                        return (self.dir_start + i, j)
            raise DirectoryFullError("Root directory is full")
        else:
            # Subdirectory - can grow
            clusters = self.follow_chain(dir_cluster)
            for cluster in clusters:
                first_sector = self._cluster_to_sector(cluster)
                for sec_offset in range(self.sectors_per_cluster):
                    sector_data = self.read_sector(first_sector + sec_offset)
                    for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                        offset = j * DIR_ENTRY_SIZE
                        first_byte = sector_data[offset]
                        if first_byte == 0x00 or first_byte == 0xE5:
                            return (cluster, sec_offset * (SECTOR_SIZE // DIR_ENTRY_SIZE) + j)

            # Need to allocate new cluster for directory
            new_cluster = self.find_free_cluster()
            if new_cluster is None:
                raise DiskFullError("No free clusters for directory expansion")

            # Link to chain
            last_cluster = clusters[-1] if clusters else dir_cluster
            self.set_fat_entry(last_cluster, new_cluster)
            self.set_fat_entry(new_cluster, 0xFFF)

            # Initialize new directory cluster with zeros
            first_sector = self._cluster_to_sector(new_cluster)
            for sec_offset in range(self.sectors_per_cluster):
                self.write_sector(first_sector + sec_offset, bytes(SECTOR_SIZE))

            return (new_cluster, 0)

    def _write_dir_entry(self, location: tuple[int, int], entry: DirectoryEntry, is_root: bool) -> None:
        """Write directory entry at specified location."""
        if is_root:
            sector_num, entry_idx = location
            offset = entry_idx * DIR_ENTRY_SIZE
        else:
            cluster, entry_idx = location
            entries_per_sector = SECTOR_SIZE // DIR_ENTRY_SIZE
            sector_in_cluster = entry_idx // entries_per_sector
            entry_in_sector = entry_idx % entries_per_sector
            sector_num = self._cluster_to_sector(cluster) + sector_in_cluster
            offset = entry_in_sector * DIR_ENTRY_SIZE

        sector_data = bytearray(self.read_sector(sector_num))
        sector_data[offset:offset + DIR_ENTRY_SIZE] = entry.to_bytes()
        self.write_sector(sector_num, bytes(sector_data))

    def write_file(self, path_components: list[str], data: bytes) -> None:
        """Write file to disk image."""
        if not path_components:
            raise InvalidFilenameError("Empty path")

        # Parse path - all but last component is directory path
        dir_path = path_components[:-1]
        filename = path_components[-1]

        # Validate filename
        name, ext = validate_filename(filename)

        # Find target directory
        if dir_path:
            dir_cluster, dir_entry = self.resolve_path(dir_path)
            if dir_entry is not None and not dir_entry.is_directory:
                raise FileNotFoundError(f"'{dir_path[-1]}' is not a directory")
            if dir_entry is not None:
                dir_cluster = dir_entry.first_cluster
        else:
            dir_cluster = None  # Root directory

        # Check if file already exists
        entries = self.read_directory(dir_cluster)
        for entry in entries:
            if entry.name == name and entry.extension == ext:
                if entry.is_directory:
                    raise DiskError(f"'{filename}' is a directory")
                # Delete existing file
                self.free_chain(entry.first_cluster)
                self._delete_entry_by_name(dir_cluster, name, ext)
                break

        # Calculate clusters needed
        num_clusters = (len(data) + self.cluster_size - 1) // self.cluster_size
        if num_clusters == 0 and len(data) == 0:
            num_clusters = 0

        # Allocate clusters
        clusters = self.allocate_chain(num_clusters) if num_clusters > 0 else []

        # Write data to clusters
        data_offset = 0
        for cluster in clusters:
            first_sector = self._cluster_to_sector(cluster)
            for sec_offset in range(self.sectors_per_cluster):
                chunk = data[data_offset:data_offset + SECTOR_SIZE]
                if len(chunk) < SECTOR_SIZE:
                    chunk = chunk + bytes(SECTOR_SIZE - len(chunk))
                self.write_sector(first_sector + sec_offset, chunk)
                data_offset += SECTOR_SIZE

        # Create directory entry
        now = time.localtime()
        date_val = ((now.tm_year - 1980) << 9) | (now.tm_mon << 5) | now.tm_mday
        time_val = (now.tm_hour << 11) | (now.tm_min << 5) | (now.tm_sec // 2)

        entry = DirectoryEntry(
            name=name,
            extension=ext,
            attributes=ATTR_ARCHIVE,
            first_cluster=clusters[0] if clusters else 0,
            file_size=len(data),
            create_time=time_val,
            create_date=date_val,
            modify_time=time_val,
            modify_date=date_val
        )

        # Find free slot and write entry
        location = self._find_free_dir_slot(dir_cluster)
        self._write_dir_entry(location, entry, dir_cluster is None)

        # Write FAT to disk
        self._write_fat()

    def _delete_entry_by_name(self, dir_cluster: int | None, name: str, ext: str) -> None:
        """Mark directory entry as deleted."""
        if dir_cluster is None:
            # Root directory
            for i in range(self.dir_sectors):
                sector_data = bytearray(self.read_sector(self.dir_start + i))
                for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                    offset = j * DIR_ENTRY_SIZE
                    entry_name = sector_data[offset:offset + 8].decode('latin-1')
                    entry_ext = sector_data[offset + 8:offset + 11].decode('latin-1')
                    if entry_name == name and entry_ext == ext:
                        sector_data[offset] = 0xE5  # Mark as deleted
                        self.write_sector(self.dir_start + i, bytes(sector_data))
                        return
        else:
            # Subdirectory
            clusters = self.follow_chain(dir_cluster)
            for cluster in clusters:
                first_sector = self._cluster_to_sector(cluster)
                for sec_offset in range(self.sectors_per_cluster):
                    sector = first_sector + sec_offset
                    sector_data = bytearray(self.read_sector(sector))
                    for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                        offset = j * DIR_ENTRY_SIZE
                        entry_name = sector_data[offset:offset + 8].decode('latin-1')
                        entry_ext = sector_data[offset + 8:offset + 11].decode('latin-1')
                        if entry_name == name and entry_ext == ext:
                            sector_data[offset] = 0xE5  # Mark as deleted
                            self.write_sector(sector, bytes(sector_data))
                            return

    def delete_file(self, path_components: list[str]) -> None:
        """Delete a file from the disk image."""
        if not path_components:
            raise InvalidFilenameError("Empty path")

        # Find the file
        dir_path = path_components[:-1]
        filename = path_components[-1]

        name, ext = validate_filename(filename)

        # Find target directory
        if dir_path:
            dir_cluster, _ = self.resolve_path(dir_path)
        else:
            dir_cluster = None

        # Find the file entry
        entries = self.read_directory(dir_cluster)
        target = None
        for entry in entries:
            if entry.name == name and entry.extension == ext:
                target = entry
                break

        if target is None:
            raise FileNotFoundError(f"File not found: {filename}")

        if target.is_directory:
            raise DiskError(f"'{filename}' is a directory, not a file")

        # Free the cluster chain
        if target.first_cluster > 0:
            self.free_chain(target.first_cluster)

        # Mark directory entry as deleted
        self._delete_entry_by_name(dir_cluster, name, ext)

        # Write FAT
        self._write_fat()

    def list_files(self, path_components: list[str] | None = None) -> list[DirectoryEntry]:
        """List files in a directory."""
        if not path_components:
            return self.read_directory(None)

        dir_cluster, entry = self.resolve_path(path_components)

        if entry is not None:
            if entry.is_directory:
                return self.read_directory(entry.first_cluster)
            else:
                # Single file
                return [entry]

        return self.read_directory(dir_cluster)

    def find_matching_files(
        self,
        path_components: list[str],
        recursive: bool = False
    ) -> list[tuple[str, DirectoryEntry]]:
        """
        Find files matching a path with optional wildcards.
        Returns list of (relative_path, entry) tuples.
        """
        if not path_components:
            return []

        last_component = path_components[-1]
        has_wildcard = has_wildcards(last_component)

        if not has_wildcard and not recursive:
            # Simple case - single file
            try:
                _, entry = self.resolve_path(path_components)
                if entry and not entry.is_directory:
                    return [(entry.full_name, entry)]
                elif entry and entry.is_directory:
                    entries = self.read_directory(entry.first_cluster)
                    return [(e.full_name, e) for e in entries if not e.is_dot_entry and not e.is_directory]
            except FileNotFoundError:
                return []
            return []

        # Determine base directory
        if len(path_components) > 1 and not has_wildcards(path_components[-2]):
            base_path = path_components[:-1]
            pattern = last_component
        elif has_wildcard:
            base_path = path_components[:-1] if len(path_components) > 1 else []
            pattern = last_component
        else:
            base_path = path_components
            pattern = '*.*'

        # Get base directory cluster
        if base_path:
            try:
                dir_cluster, entry = self.resolve_path(base_path)
                if entry is not None and entry.is_directory:
                    dir_cluster = entry.first_cluster
            except FileNotFoundError:
                return []
        else:
            dir_cluster = None

        results = []

        if recursive:
            # Recursive search - include directories in results
            def recurse(cluster: int | None, rel_path: str):
                entries = self.read_directory(cluster)
                for entry in entries:
                    if entry.is_dot_entry:
                        continue
                    entry_rel = rel_path + '\\' + entry.full_name if rel_path else entry.full_name
                    if entry.is_directory:
                        # Add directory to results, then recurse into it
                        results.append((entry_rel, entry))
                        recurse(entry.first_cluster, entry_rel)
                    elif match_filename(pattern, entry.full_name):
                        results.append((entry_rel, entry))

            recurse(dir_cluster, '')
        else:
            # Non-recursive
            entries = self.read_directory(dir_cluster)
            for entry in entries:
                if entry.is_dot_entry or entry.is_directory:
                    continue
                if match_filename(pattern, entry.full_name):
                    results.append((entry.full_name, entry))

        return results

    def get_attributes(self, path_components: list[str]) -> int:
        """Get file attributes."""
        entry = self.find_entry(path_components)
        return entry.attributes

    def set_attributes(self, path_components: list[str], attributes: int) -> None:
        """
        Set file attributes.

        Args:
            path_components: Path to the file
            attributes: New attribute byte value
        """
        if not path_components:
            raise InvalidFilenameError("Empty path")

        # Find the file
        dir_path = path_components[:-1]
        filename = path_components[-1]

        name, ext = validate_filename(filename)

        # Find target directory
        if dir_path:
            dir_cluster, _ = self.resolve_path(dir_path)
        else:
            dir_cluster = None

        # Find and update the entry
        self._update_entry_attributes(dir_cluster, name, ext, attributes)

    def _update_entry_attributes(
        self,
        dir_cluster: int | None,
        name: str,
        ext: str,
        attributes: int
    ) -> None:
        """Update attributes in a directory entry."""
        if dir_cluster is None:
            # Root directory
            for i in range(self.dir_sectors):
                sector_data = bytearray(self.read_sector(self.dir_start + i))
                for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                    offset = j * DIR_ENTRY_SIZE
                    entry_name = sector_data[offset:offset + 8].decode('latin-1')
                    entry_ext = sector_data[offset + 8:offset + 11].decode('latin-1')
                    if entry_name == name and entry_ext == ext:
                        # Preserve directory bit, update others
                        old_attrs = sector_data[offset + 11]
                        new_attrs = (old_attrs & ATTR_DIRECTORY) | (attributes & ~ATTR_DIRECTORY)
                        sector_data[offset + 11] = new_attrs
                        self.write_sector(self.dir_start + i, bytes(sector_data))
                        return
            raise FileNotFoundError(f"File not found: {name.strip()}.{ext.strip()}")
        else:
            # Subdirectory
            clusters = self.follow_chain(dir_cluster)
            for cluster in clusters:
                first_sector = self._cluster_to_sector(cluster)
                for sec_offset in range(self.sectors_per_cluster):
                    sector = first_sector + sec_offset
                    sector_data = bytearray(self.read_sector(sector))
                    for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                        offset = j * DIR_ENTRY_SIZE
                        entry_name = sector_data[offset:offset + 8].decode('latin-1')
                        entry_ext = sector_data[offset + 8:offset + 11].decode('latin-1')
                        if entry_name == name and entry_ext == ext:
                            # Preserve directory bit, update others
                            old_attrs = sector_data[offset + 11]
                            new_attrs = (old_attrs & ATTR_DIRECTORY) | (attributes & ~ATTR_DIRECTORY)
                            sector_data[offset + 11] = new_attrs
                            self.write_sector(sector, bytes(sector_data))
                            return
            raise FileNotFoundError(f"File not found: {name.strip()}.{ext.strip()}")

    def rename_entry(self, path_components: list[str], new_name: str) -> None:
        """
        Rename a file or directory.

        Args:
            path_components: Path to the file/directory to rename
            new_name: New filename (8.3 format, e.g., "NEWNAME.TXT")
        """
        if not path_components:
            raise InvalidFilenameError("Empty path")

        # Parse old and new names
        dir_path = path_components[:-1]
        old_filename = path_components[-1]

        old_name, old_ext = validate_filename(old_filename)
        new_name_part, new_ext = validate_filename(new_name)

        # Find target directory
        if dir_path:
            dir_cluster, _ = self.resolve_path(dir_path)
        else:
            dir_cluster = None

        # Check that the new name doesn't already exist (unless it's the same)
        if old_name != new_name_part or old_ext != new_ext:
            entries = self.read_directory(dir_cluster)
            for entry in entries:
                if entry.name == new_name_part and entry.extension == new_ext:
                    raise DiskError(f"File already exists: {new_name}")

        # Find and update the entry
        self._rename_entry_in_dir(dir_cluster, old_name, old_ext, new_name_part, new_ext)

    def _rename_entry_in_dir(
        self,
        dir_cluster: int | None,
        old_name: str,
        old_ext: str,
        new_name: str,
        new_ext: str
    ) -> None:
        """Update name/extension in a directory entry."""
        new_name_bytes = new_name.encode('latin-1')
        new_ext_bytes = new_ext.encode('latin-1')

        if dir_cluster is None:
            # Root directory
            for i in range(self.dir_sectors):
                sector_data = bytearray(self.read_sector(self.dir_start + i))
                for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                    offset = j * DIR_ENTRY_SIZE
                    entry_name = sector_data[offset:offset + 8].decode('latin-1')
                    entry_ext = sector_data[offset + 8:offset + 11].decode('latin-1')
                    if entry_name == old_name and entry_ext == old_ext:
                        # Update name and extension
                        sector_data[offset:offset + 8] = new_name_bytes
                        sector_data[offset + 8:offset + 11] = new_ext_bytes
                        self.write_sector(self.dir_start + i, bytes(sector_data))
                        return
            raise FileNotFoundError(f"File not found: {old_name.strip()}.{old_ext.strip()}")
        else:
            # Subdirectory
            clusters = self.follow_chain(dir_cluster)
            for cluster in clusters:
                first_sector = self._cluster_to_sector(cluster)
                for sec_offset in range(self.sectors_per_cluster):
                    sector = first_sector + sec_offset
                    sector_data = bytearray(self.read_sector(sector))
                    for j in range(SECTOR_SIZE // DIR_ENTRY_SIZE):
                        offset = j * DIR_ENTRY_SIZE
                        entry_name = sector_data[offset:offset + 8].decode('latin-1')
                        entry_ext = sector_data[offset + 8:offset + 11].decode('latin-1')
                        if entry_name == old_name and entry_ext == old_ext:
                            # Update name and extension
                            sector_data[offset:offset + 8] = new_name_bytes
                            sector_data[offset + 8:offset + 11] = new_ext_bytes
                            self.write_sector(sector, bytes(sector_data))
                            return
            raise FileNotFoundError(f"File not found: {old_name.strip()}.{old_ext.strip()}")

    def flush(self) -> None:
        """Flush any pending FAT changes to disk."""
        if self._fat_dirty:
            self._write_fat()

    def create_directory(self, path_components: list[str]) -> None:
        """
        Create a directory on the disk image.

        Args:
            path_components: Path to the new directory (e.g., ['SUBDIR'] or ['DIR1', 'DIR2'])
        """
        if not path_components:
            raise InvalidFilenameError("Empty path")

        # Parse path - all but last component is parent directory path
        parent_path = path_components[:-1]
        dirname = path_components[-1]

        # Validate directory name
        name, ext = validate_filename(dirname)

        # Find parent directory
        if parent_path:
            parent_cluster, parent_entry = self.resolve_path(parent_path)
            if parent_entry is not None and not parent_entry.is_directory:
                raise FileNotFoundError(f"'{parent_path[-1]}' is not a directory")
            if parent_entry is not None:
                parent_cluster = parent_entry.first_cluster
        else:
            parent_cluster = None  # Root directory

        # Check if directory already exists
        entries = self.read_directory(parent_cluster)
        for entry in entries:
            if entry.name == name and entry.extension == ext:
                if entry.is_directory:
                    return  # Directory already exists, nothing to do
                raise DiskError(f"'{dirname}' already exists as a file")

        # Allocate a cluster for the new directory
        new_cluster = self.find_free_cluster()
        if new_cluster is None:
            raise DiskFullError("No free clusters for directory")

        self.set_fat_entry(new_cluster, 0xFFF)  # Mark as end of chain

        # Initialize directory cluster with zeros
        first_sector = self._cluster_to_sector(new_cluster)
        for sec_offset in range(self.sectors_per_cluster):
            self.write_sector(first_sector + sec_offset, bytes(SECTOR_SIZE))

        # Create timestamp
        now = time.localtime()
        date_val = ((now.tm_year - 1980) << 9) | (now.tm_mon << 5) | now.tm_mday
        time_val = (now.tm_hour << 11) | (now.tm_min << 5) | (now.tm_sec // 2)

        # Create "." entry (points to self)
        dot_entry = DirectoryEntry(
            name='.       ',
            extension='   ',
            attributes=ATTR_DIRECTORY,
            first_cluster=new_cluster,
            file_size=0,
            create_time=time_val,
            create_date=date_val,
            modify_time=time_val,
            modify_date=date_val
        )

        # Create ".." entry (points to parent)
        dotdot_entry = DirectoryEntry(
            name='..      ',
            extension='   ',
            attributes=ATTR_DIRECTORY,
            first_cluster=parent_cluster or 0,  # 0 for root
            file_size=0,
            create_time=time_val,
            create_date=date_val,
            modify_time=time_val,
            modify_date=date_val
        )

        # Write "." and ".." entries to new directory
        sector_data = bytearray(SECTOR_SIZE)
        sector_data[0:DIR_ENTRY_SIZE] = dot_entry.to_bytes()
        sector_data[DIR_ENTRY_SIZE:DIR_ENTRY_SIZE * 2] = dotdot_entry.to_bytes()
        self.write_sector(first_sector, bytes(sector_data))

        # Create directory entry in parent
        dir_entry = DirectoryEntry(
            name=name,
            extension=ext,
            attributes=ATTR_DIRECTORY,
            first_cluster=new_cluster,
            file_size=0,
            create_time=time_val,
            create_date=date_val,
            modify_time=time_val,
            modify_date=date_val
        )

        # Find free slot in parent and write entry
        location = self._find_free_dir_slot(parent_cluster)
        self._write_dir_entry(location, dir_entry, parent_cluster is None)

        # Write FAT to disk
        self._write_fat()

    def delete_directory(self, path_components: list[str], recursive: bool = False) -> None:
        """
        Delete a directory from the disk image.

        Args:
            path_components: Path to the directory
            recursive: If True, delete contents recursively. If False, directory must be empty.
        """
        if not path_components:
            raise InvalidFilenameError("Empty path")

        # Find the directory
        dir_path = path_components[:-1]
        dirname = path_components[-1]

        name, ext = validate_filename(dirname)

        # Find parent directory
        if dir_path:
            parent_cluster, _ = self.resolve_path(dir_path)
        else:
            parent_cluster = None

        # Find the directory entry
        entries = self.read_directory(parent_cluster)
        target = None
        for entry in entries:
            if entry.name == name and entry.extension == ext:
                target = entry
                break

        if target is None:
            raise FileNotFoundError(f"Directory not found: {dirname}")

        if not target.is_directory:
            raise DiskError(f"'{dirname}' is not a directory")

        # Check if directory is empty (except . and ..)
        dir_contents = self.read_directory(target.first_cluster)
        non_dot_entries = [e for e in dir_contents if not e.is_dot_entry]

        if non_dot_entries and not recursive:
            raise DiskError(f"Directory '{dirname}' is not empty")

        if recursive:
            # Delete contents recursively
            for entry in non_dot_entries:
                entry_path = path_components + [entry.full_name]
                if entry.is_directory:
                    self.delete_directory(entry_path, recursive=True)
                else:
                    self.delete_file(entry_path)

        # Free the directory's cluster chain
        if target.first_cluster > 0:
            self.free_chain(target.first_cluster)

        # Mark directory entry as deleted in parent
        self._delete_entry_by_name(parent_cluster, name, ext)

        # Write FAT
        self._write_fat()


class DiskImageFileMixin:
    """
    Mixin providing file-based sector I/O for standalone disk images.
    Used by V9KDiskImage and IBMPCDiskImage (not V9KPartition).
    """

    image_path: str
    readonly: bool
    _file: BinaryIO | None

    def _open_file(self, image_path: str, readonly: bool) -> None:
        """Open the disk image file."""
        self.image_path = image_path
        self.readonly = readonly
        mode = 'rb' if readonly else 'r+b'
        try:
            self._file = open(image_path, mode)
        except OSError as e:
            raise DiskError(f"Cannot open disk image: {e}")

    def read_sector(self, sector_num: int) -> bytes:
        """Read a single sector from the disk image."""
        if self._file is None:
            raise DiskError("Disk image not open")

        offset = sector_num * SECTOR_SIZE
        self._file.seek(offset)
        data = self._file.read(SECTOR_SIZE)

        if len(data) < SECTOR_SIZE:
            data = data + bytes(SECTOR_SIZE - len(data))

        return data

    def write_sector(self, sector_num: int, data: bytes) -> None:
        """Write a single sector to the disk image."""
        if self._file is None:
            raise DiskError("Disk image not open")
        if self.readonly:
            raise DiskError("Disk image opened in read-only mode")

        if len(data) != SECTOR_SIZE:
            raise DiskError(f"Invalid sector size: {len(data)}")

        offset = sector_num * SECTOR_SIZE
        self._file.seek(offset)
        self._file.write(data)

    def flush(self) -> None:
        """Flush any pending changes to disk."""
        super().flush()  # type: ignore  # Calls FAT12Base.flush()
        if self._file:
            self._file.flush()

    def close(self) -> None:
        """Close the disk image."""
        self.flush()
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
