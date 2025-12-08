"""
Victor 9000 hard disk image classes.
"""

from typing import BinaryIO

from .constants import (
    DIR_ENTRY_SIZE,
    HD_MAX_DIR_ENTRIES,
    HD_SECTORS_PER_CLUSTER,
    SECTOR_SIZE,
)
from .exceptions import DiskError, InvalidPartitionError
from .fat12 import FAT12Base
from .models import DirectoryEntry, PhysicalDiskLabel, VirtualVolumeLabel


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

        # Calculate FAT size based on cluster count (FAT12 uses 1.5 bytes/cluster)
        total_data_sectors = volume_label.volume_capacity
        estimated_clusters = total_data_sectors // self._sectors_per_cluster
        fat_bytes = (estimated_clusters * 3 + 1) // 2
        self._fat_sectors = max(1, (fat_bytes + SECTOR_SIZE - 1) // SECTOR_SIZE)

        # Calculate layout relative to volume start
        self._volume_start = volume_label.volume_start_sector
        self._fat_start = self._volume_start + 1  # FAT starts after volume label
        self._dir_start = self._fat_start + (2 * self._fat_sectors)  # After both FAT copies
        self._data_start = self._dir_start + self._dir_sectors

        # Calculate total clusters
        volume_data_sectors = volume_label.volume_capacity - (1 + 2 * self._fat_sectors + self._dir_sectors)
        self._total_clusters = volume_data_sectors // self._sectors_per_cluster

        # Initialize base class and load FAT
        FAT12Base.__init__(self)
        self._load_fat()

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
    """

    def __init__(self, image_path: str, readonly: bool = True):
        self.image_path = image_path
        self.readonly = readonly
        self._file: BinaryIO | None = None
        self._physical_label: PhysicalDiskLabel | None = None
        self._partitions: list[V9KPartition] = []

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
                'cluster_size': p._cluster_size
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
