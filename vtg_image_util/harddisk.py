"""
Victor 9000 hard disk image classes.

Supports both raw disk images (.img) and CHD container format (.chd).
"""

from typing import BinaryIO, Protocol

from .constants import (
    DIR_ENTRY_SIZE,
    HD_MAX_DIR_ENTRIES,
    HD_SECTORS_PER_CLUSTER,
    SECTOR_SIZE,
)
from .exceptions import DiskError, InvalidPartitionError
from .fat12 import FAT12Base
from .models import DirectoryEntry, PhysicalDiskLabel, VirtualVolumeLabel


class FileInterface(Protocol):
    """Protocol for file-like objects used by V9KHardDiskImage."""
    def seek(self, offset: int, whence: int = 0) -> int: ...
    def read(self, size: int = -1) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


class V9KPartition(FAT12Base):
    """
    Represents a single partition (virtual volume) on a hard disk.

    Unlike floppy disk images, V9KPartition does not own its file handle.
    It delegates sector I/O to the parent V9KHardDiskImage.
    """

    def __init__(
        self,
        disk: 'V9KHardDiskImage',
        partition_index: int,
        volume_label: VirtualVolumeLabel
    ):
        self.disk = disk
        self.partition_index = partition_index
        self.volume_label = volume_label
        self.readonly = disk.readonly

        # Partition geometry from volume label
        self._sectors_per_cluster = volume_label.allocation_unit or HD_SECTORS_PER_CLUSTER
        self._cluster_size = SECTOR_SIZE * self._sectors_per_cluster
        self._max_dir_entries = volume_label.num_dir_entries or HD_MAX_DIR_ENTRIES

        # Calculate directory sectors from entry count
        entries_per_sector = SECTOR_SIZE // DIR_ENTRY_SIZE
        self._dir_sectors = (self._max_dir_entries + entries_per_sector - 1) // entries_per_sector

        # Calculate layout relative to volume start
        self._volume_start = volume_label.volume_start_sector
        self._fat_start = self._volume_start + 1  # FAT starts after volume label

        # Detect actual FAT size by finding where directory starts
        # FAT sectors typically start with media descriptor (0xF8) or are all 0xFF/0x00
        # Directory sectors start with valid 8.3 filename characters
        self._fat_sectors = self._detect_fat_size()

        self._dir_start = self._fat_start + (2 * self._fat_sectors)  # After both FAT copies
        self._data_start = self._dir_start + self._dir_sectors

        # Calculate total clusters
        volume_data_sectors = volume_label.volume_capacity - (1 + 2 * self._fat_sectors + self._dir_sectors)
        self._total_clusters = volume_data_sectors // self._sectors_per_cluster

        # Initialize base class and load FAT
        FAT12Base.__init__(self)
        self._load_fat()

    # =========================================================================
    # Layout Detection
    # =========================================================================

    def _detect_fat_size(self) -> int:
        """
        Detect actual FAT size by scanning for where directory starts.

        Victor 9000 hard disk FAT size may not match capacity-based estimates.
        We find the directory start by looking for the first sector that contains
        valid directory entries (not FAT data).

        Returns the number of sectors per FAT copy.
        """
        # Estimate FAT size as upper bound for scanning
        total_data_sectors = self.volume_label.volume_capacity
        estimated_clusters = total_data_sectors // self._sectors_per_cluster
        fat_bytes = (estimated_clusters * 3 + 1) // 2
        max_fat_sectors = max(1, (fat_bytes + SECTOR_SIZE - 1) // SECTOR_SIZE)

        # Scan from offset 1 to find where directory starts
        # Directory will be after 2 FAT copies, so scan up to max_fat_sectors * 2 + some margin
        max_scan = min(max_fat_sectors * 2 + 10, 100)

        for offset in range(1, max_scan + 1):
            sector_num = self._volume_start + offset
            try:
                data = self.disk.read_sector(sector_num)
            except Exception:
                continue

            # Check if this sector looks like a directory entry
            if self._is_directory_sector(data):
                # Directory starts here, so FAT ends at offset-1
                # With 2 FAT copies: offset = 1 + fat_sectors + fat_sectors
                # So fat_sectors = (offset - 1) / 2
                fat_sectors = (offset - 1) // 2
                return max(1, fat_sectors)

        # Fallback to estimated size if detection fails
        return max_fat_sectors

    def _is_directory_sector(self, data: bytes) -> bool:
        """
        Check if a sector contains directory entries (not FAT data).

        FAT sectors typically start with 0xF8 (media descriptor) or contain
        mostly 0xFF/0x00 bytes. Directory sectors contain 8.3 filenames.
        """
        if len(data) < 32:
            return False

        first_byte = data[0]

        # FAT starts with media descriptor byte (usually 0xF8)
        if first_byte == 0xF8:
            return False

        # Empty sector (all zeros) is not a directory with entries
        if first_byte == 0x00:
            # But could be end-of-directory marker - check if previous was dir
            return False

        # Deleted entry marker
        if first_byte == 0xE5:
            # Could be directory with deleted entries, check more
            pass

        # Check if first entry looks like valid 8.3 filename
        # Valid filename chars: A-Z, 0-9, space, and some special chars
        name_bytes = data[0:8]
        ext_bytes = data[8:11]
        attr = data[11]

        # Attribute must be valid (0x00-0x3F, but not 0x0F which is LFN)
        if attr > 0x3F or attr == 0x0F:
            return False

        # For non-deleted entries, check filename characters
        if first_byte != 0xE5:
            for b in name_bytes:
                # Valid: A-Z (0x41-0x5A), 0-9 (0x30-0x39), space (0x20),
                # special chars, or dot for . and .. entries
                if b == 0x20:  # Space padding
                    continue
                if 0x41 <= b <= 0x5A:  # A-Z
                    continue
                if 0x30 <= b <= 0x39:  # 0-9
                    continue
                if b == 0x2E:  # Dot (for . and .. entries)
                    continue
                if b in (0x21, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29,
                         0x2D, 0x40, 0x5E, 0x5F, 0x60, 0x7B, 0x7D, 0x7E):
                    continue  # Special chars !#$%&'()-@^_`{}~
                return False

            for b in ext_bytes:
                if b == 0x20:
                    continue
                if 0x41 <= b <= 0x5A:
                    continue
                if 0x30 <= b <= 0x39:
                    continue
                if b in (0x21, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29,
                         0x2D, 0x40, 0x5E, 0x5F, 0x60, 0x7B, 0x7D, 0x7E):
                    continue
                return False

        return True

    # =========================================================================
    # Sector I/O - Delegate to parent disk
    # =========================================================================

    def read_sector(self, sector_num: int) -> bytes:
        """Read a single sector by delegating to parent disk."""
        return self.disk.read_sector(sector_num)

    def write_sector(self, sector_num: int, data: bytes) -> None:
        """Write a single sector by delegating to parent disk."""
        self.disk.write_sector(sector_num, data)

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
        return 2  # Victor hard disk uses 2 FAT copies

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
        return self._sectors_per_cluster

    @property
    def cluster_size(self) -> int:
        return self._cluster_size


class V9KHardDiskImage:
    """
    Victor 9000 hard disk image with multiple partitions.

    Provides raw sector I/O that partitions delegate to.
    Supports both raw disk images and CHD container format.
    """

    def __init__(self, image_path: str, readonly: bool = True):
        self.image_path = image_path
        self.readonly = readonly
        self._file: FileInterface | None = None
        self._physical_label: PhysicalDiskLabel | None = None
        self._partitions: list[V9KPartition] = []
        self._is_chd: bool = False

        # Check if this is a CHD file
        try:
            with open(image_path, 'rb') as f:
                sig = f.read(8)
                self._is_chd = (sig == b'MComprHD')
        except OSError:
            self._is_chd = False

        if self._is_chd:
            # Use CHD wrapper (read-only)
            if not readonly:
                raise DiskError("CHD files are read-only")
            from .chd import CHDFile, CHDError
            try:
                self._file = CHDFile(image_path)
            except CHDError:
                raise  # Re-raise CHDError directly for proper handling
            except Exception as e:
                raise DiskError(f"Cannot open CHD file: {e}")
        else:
            # Use raw file
            mode = 'rb' if readonly else 'r+b'
            try:
                self._file = open(image_path, mode)
            except OSError as e:
                raise DiskError(f"Cannot open disk image: {e}")

        self._read_physical_label()
        self._load_partitions()

    def _read_physical_label(self) -> None:
        """Parse the physical disk label from sector 0."""
        data = self.read_sector(0) + self.read_sector(1)
        self._physical_label = PhysicalDiskLabel.from_bytes(data)

    def _load_partitions(self) -> None:
        """Load all virtual volumes as partitions."""
        if self._physical_label is None:
            return

        for idx, volume_addr in enumerate(self._physical_label.virtual_volume_addresses):
            volume_data = self.read_sector(volume_addr)
            volume_label = VirtualVolumeLabel.from_bytes(volume_data, volume_addr)

            # Validate volume label - skip if it appears to be garbage data
            # Valid label_type values: 0x0000 (null), 0x0001, 0x0002, 0xFFFF (maintenance)
            valid_label_types = (0x0000, 0x0001, 0x0002, 0xFFFF)
            if volume_label.label_type not in valid_label_types:
                continue  # Skip invalid/uninitialized volume labels

            partition = V9KPartition(self, idx, volume_label)
            self._partitions.append(partition)

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

    def get_partition(self, index: int) -> V9KPartition:
        """Get partition by index."""
        if index < 0 or index >= len(self._partitions):
            raise InvalidPartitionError(
                f"Invalid partition index: {index}. "
                f"Valid range: 0-{len(self._partitions) - 1}"
            )
        return self._partitions[index]

    @property
    def partition_count(self) -> int:
        return len(self._partitions)

    def list_partitions(self) -> list[dict]:
        """Return info about all partitions."""
        return [
            {
                'index': i,
                'name': p.volume_label.volume_name.strip(),
                'capacity': p.volume_label.volume_capacity,
                'capacity_bytes': p.volume_label.volume_capacity * SECTOR_SIZE,
                'cluster_size': p._cluster_size,
                'assignments': [
                    {'device_unit': a.device_unit, 'volume_index': a.volume_index}
                    for a in p.volume_label.assignments
                ]
            }
            for i, p in enumerate(self._partitions)
        ]

    def flush(self) -> None:
        """Flush any pending changes to disk."""
        for partition in self._partitions:
            partition.flush()
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
