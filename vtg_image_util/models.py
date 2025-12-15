"""
Data model classes for Victor 9000 and IBM PC disk image utilities.
"""

import struct
from dataclasses import dataclass

from .constants import (
    ATTR_ARCHIVE,
    ATTR_DIRECTORY,
    ATTR_HIDDEN,
    ATTR_READONLY,
    ATTR_SYSTEM,
    ATTR_VOLUME,
    CPM_DELETED,
    CPM_RECORD_SIZE,
    PDL_CONTROLLER_PARAMS,
    PDL_DEVICE_ID,
    PDL_IPL_DISK_ADDR,
    PDL_IPL_LOAD_ADDR,
    PDL_IPL_LOAD_LEN,
    PDL_IPL_CODE_ENTRY,
    PDL_LABEL_TYPE,
    PDL_PRIMARY_BOOT_VOL,
    PDL_SECTOR_SIZE,
    PDL_SERIAL_NUMBER,
    VVL_ALLOCATION_UNIT,
    VVL_ASSIGNMENT_COUNT,
    VVL_DATA_START,
    VVL_HOST_BLOCK_SIZE,
    VVL_IPL_DISK_ADDR,
    VVL_LABEL_TYPE,
    VVL_NUM_DIR_ENTRIES,
    VVL_VOLUME_CAPACITY,
    VVL_VOLUME_NAME,
)
from .exceptions import DiskError, HardDiskLabelError


@dataclass
class DirectoryEntry:
    """Represents a 32-byte FAT directory entry."""
    name: str           # 8 chars, space-padded
    extension: str      # 3 chars, space-padded
    attributes: int     # Attribute byte
    first_cluster: int  # Starting cluster number
    file_size: int      # Size in bytes

    # Timestamps (not fully used but preserved)
    create_time: int = 0
    create_date: int = 0
    modify_time: int = 0
    modify_date: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> 'DirectoryEntry':
        """Parse a 32-byte directory entry."""
        if len(data) != 32:
            raise DiskError(f"Invalid directory entry size: {len(data)}")

        # Decode with latin-1 to handle any byte value, then sanitize
        name = data[0:8].decode('latin-1')
        ext = data[8:11].decode('latin-1')
        attr = data[11]
        create_time = struct.unpack_from('<H', data, 14)[0]
        create_date = struct.unpack_from('<H', data, 16)[0]
        modify_time = struct.unpack_from('<H', data, 22)[0]
        modify_date = struct.unpack_from('<H', data, 24)[0]
        first_cluster = struct.unpack_from('<H', data, 26)[0]
        file_size = struct.unpack_from('<I', data, 28)[0]

        return cls(
            name=name,
            extension=ext,
            attributes=attr,
            first_cluster=first_cluster,
            file_size=file_size,
            create_time=create_time,
            create_date=create_date,
            modify_time=modify_time,
            modify_date=modify_date
        )

    def to_bytes(self) -> bytes:
        """Serialize to 32-byte directory entry."""
        data = bytearray(32)
        data[0:8] = self.name.encode('ascii')[:8].ljust(8)
        data[8:11] = self.extension.encode('ascii')[:3].ljust(3)
        data[11] = self.attributes
        struct.pack_into('<H', data, 14, self.create_time)
        struct.pack_into('<H', data, 16, self.create_date)
        struct.pack_into('<H', data, 22, self.modify_time)
        struct.pack_into('<H', data, 24, self.modify_date)
        struct.pack_into('<H', data, 26, self.first_cluster)
        struct.pack_into('<I', data, 28, self.file_size)
        return bytes(data)

    @property
    def full_name(self) -> str:
        """Return 'NAME.EXT' format."""
        name = self.name.rstrip()
        ext = self.extension.rstrip()
        if ext:
            return f"{name}.{ext}"
        return name

    @property
    def is_free(self) -> bool:
        """Check if entry is free (deleted or never used)."""
        first_byte = ord(self.name[0]) if self.name else 0
        return first_byte == 0x00 or first_byte == 0xE5

    @property
    def is_end(self) -> bool:
        """Check if this marks end of directory."""
        first_byte = ord(self.name[0]) if self.name else 0
        return first_byte == 0x00

    @property
    def is_deleted(self) -> bool:
        """Check if entry is deleted."""
        first_byte = ord(self.name[0]) if self.name else 0
        return first_byte == 0xE5

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & ATTR_DIRECTORY)

    @property
    def is_volume_label(self) -> bool:
        return bool(self.attributes & ATTR_VOLUME)

    @property
    def is_dot_entry(self) -> bool:
        """Check if this is . or .. entry."""
        return self.name.startswith('.')

    def attr_string(self) -> str:
        """Return attribute string like 'RHSDA'."""
        attrs = []
        if self.attributes & ATTR_READONLY:
            attrs.append('R')
        if self.attributes & ATTR_HIDDEN:
            attrs.append('H')
        if self.attributes & ATTR_SYSTEM:
            attrs.append('S')
        if self.attributes & ATTR_DIRECTORY:
            attrs.append('D')
        if self.attributes & ATTR_ARCHIVE:
            attrs.append('A')
        return ''.join(attrs) if attrs else '-'


@dataclass
class CPMDirectoryEntry:
    """Represents a 32-byte CP/M directory entry."""
    user: int               # User number (0-15)
    filename: str           # 8 chars, space-padded
    extension: str          # 3 chars, space-padded (high bits may be attributes)
    extent: int             # Combined extent number (S2*32 + EL)
    record_count: int       # Records in this extent (0-128)
    blocks: list[int]       # Allocation block numbers (up to 16)
    is_deleted: bool        # True if user byte was 0xE5
    # Store raw extension bytes for attribute extraction
    _ext_raw: bytes = b'\x00\x00\x00'

    @classmethod
    def from_bytes(cls, data: bytes) -> 'CPMDirectoryEntry':
        """Parse a 32-byte CP/M directory entry."""
        if len(data) != 32:
            raise DiskError(f"Invalid CP/M directory entry size: {len(data)}")

        user = data[0]
        is_deleted = (user == CPM_DELETED)

        # Filename: bytes 1-8, mask off high bit (used for flags in some systems)
        filename = bytes([b & 0x7F for b in data[1:9]]).decode('ascii', errors='replace').rstrip()

        # Extension: bytes 9-11, high bits are attributes
        ext_raw = data[9:12]
        extension = bytes([b & 0x7F for b in ext_raw]).decode('ascii', errors='replace').rstrip()

        # Extent number: EL (byte 12) + S2 (byte 14) * 32
        el = data[12]
        s2 = data[14]
        extent = s2 * 32 + el

        # Record count (byte 15)
        record_count = data[15]

        # Allocation blocks (bytes 16-31): 8 x 16-bit block numbers (little-endian)
        blocks = []
        for i in range(8):
            block = struct.unpack_from('<H', data, 16 + i * 2)[0]
            if block != 0:
                blocks.append(block)

        return cls(
            user=user if not is_deleted else 0,
            filename=filename,
            extension=extension,
            extent=extent,
            record_count=record_count,
            blocks=blocks,
            is_deleted=is_deleted,
            _ext_raw=ext_raw
        )

    def to_bytes(self) -> bytes:
        """Serialize to 32-byte CP/M directory entry."""
        data = bytearray(32)

        # User number (or 0xE5 if deleted)
        data[0] = CPM_DELETED if self.is_deleted else self.user

        # Filename (space-padded)
        fname = self.filename.ljust(8)[:8].encode('ascii')
        data[1:9] = fname

        # Extension (space-padded, preserve high bits if we have them)
        ext = self.extension.ljust(3)[:3].encode('ascii')
        if self._ext_raw != b'\x00\x00\x00':
            # Preserve attribute bits from original
            for i in range(3):
                data[9 + i] = (self._ext_raw[i] & 0x80) | (ext[i] & 0x7F)
        else:
            data[9:12] = ext

        # Extent: EL and S2
        data[12] = self.extent % 32       # EL
        data[13] = 0                       # S1 (reserved)
        data[14] = self.extent // 32       # S2

        # Record count
        data[15] = self.record_count

        # Allocation blocks (8 x 16-bit, pad with zeros)
        for i, block in enumerate(self.blocks[:8]):
            struct.pack_into('<H', data, 16 + i * 2, block)

        return bytes(data)

    @property
    def full_name(self) -> str:
        """Return 'NAME.EXT' format."""
        if self.extension:
            return f"{self.filename}.{self.extension}"
        return self.filename

    @property
    def is_read_only(self) -> bool:
        """Check if read-only attribute is set (high bit of ext[0])."""
        return bool(self._ext_raw[0] & 0x80) if len(self._ext_raw) > 0 else False

    @property
    def is_system(self) -> bool:
        """Check if system attribute is set (high bit of ext[1])."""
        return bool(self._ext_raw[1] & 0x80) if len(self._ext_raw) > 1 else False

    @property
    def is_archive(self) -> bool:
        """Check if archive attribute is set (high bit of ext[2])."""
        return bool(self._ext_raw[2] & 0x80) if len(self._ext_raw) > 2 else False

    @property
    def file_size(self) -> int:
        """Calculate file size in bytes from record count and blocks.

        Note: This is an approximation for a single extent. For multi-extent
        files, the caller must combine all extents.
        """
        return self.record_count * CPM_RECORD_SIZE

    @property
    def is_directory(self) -> bool:
        """CP/M doesn't have directories in the FAT sense."""
        return False

    def attr_string(self) -> str:
        """Return attribute string like 'RS'."""
        attrs = []
        if self.is_read_only:
            attrs.append('R')
        if self.is_system:
            attrs.append('S')
        if self.is_archive:
            attrs.append('A')
        return ''.join(attrs) if attrs else '-'


@dataclass
class PhysicalDiskLabel:
    """Physical disk label at sector 0 of hard disk."""
    label_type: int
    device_id: int
    serial_number: str
    sector_size: int
    ipl_disk_address: int
    ipl_load_address: int
    ipl_load_length: int
    ipl_code_entry: int
    primary_boot_volume: int
    controller_params: bytes
    virtual_volume_addresses: list[int]

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PhysicalDiskLabel':
        """Parse physical disk label from sector 0-1 data."""
        if len(data) < 512:
            raise HardDiskLabelError("Insufficient data for physical disk label")

        label_type = struct.unpack_from('<H', data, PDL_LABEL_TYPE)[0]
        device_id = struct.unpack_from('<H', data, PDL_DEVICE_ID)[0]
        serial_number = data[PDL_SERIAL_NUMBER:PDL_SERIAL_NUMBER + 16].decode('ascii', errors='replace').strip('\x00')
        sector_size = struct.unpack_from('<H', data, PDL_SECTOR_SIZE)[0]
        ipl_disk_address = struct.unpack_from('<I', data, PDL_IPL_DISK_ADDR)[0]
        ipl_load_address = struct.unpack_from('<H', data, PDL_IPL_LOAD_ADDR)[0]
        ipl_load_length = struct.unpack_from('<H', data, PDL_IPL_LOAD_LEN)[0]
        ipl_code_entry = struct.unpack_from('<I', data, PDL_IPL_CODE_ENTRY)[0]
        primary_boot_volume = struct.unpack_from('<H', data, PDL_PRIMARY_BOOT_VOL)[0]
        controller_params = data[PDL_CONTROLLER_PARAMS:PDL_CONTROLLER_PARAMS + 16]

        # Parse variable-length lists after controller params
        offset = PDL_CONTROLLER_PARAMS + 16  # 52

        # Available media list
        avail_region_count = data[offset]
        offset += 1
        # Skip available media regions (8 bytes each: 4-byte address + 4-byte size)
        offset += avail_region_count * 8

        # Working media list
        work_region_count = data[offset]
        offset += 1
        # Skip working media regions (8 bytes each)
        offset += work_region_count * 8

        # Virtual volume list
        volume_count = data[offset]
        offset += 1
        virtual_volume_addresses = []
        for _ in range(volume_count):
            addr = struct.unpack_from('<I', data, offset)[0]
            virtual_volume_addresses.append(addr)
            offset += 4      

        return cls(
            label_type=label_type,
            device_id=device_id,
            serial_number=serial_number,
            sector_size=sector_size,
            ipl_disk_address=ipl_disk_address,
            ipl_load_address=ipl_load_address,
            ipl_load_length=ipl_load_length,
            ipl_code_entry=ipl_code_entry,
            primary_boot_volume=primary_boot_volume,
            controller_params=controller_params,
            virtual_volume_addresses=virtual_volume_addresses
        )


@dataclass
class DriveAssignment:
    """Drive assignment mapping from Configuration Information."""
    device_unit: int    # Physical unit number
    volume_index: int   # Index into virtual volume list


@dataclass
class VirtualVolumeLabel:
    """Virtual volume label for a partition."""
    label_type: int
    volume_name: str
    ipl_disk_address: int
    ipl_load_address: int
    ipl_load_length: int
    ipl_code_entry: int
    volume_capacity: int
    data_start: int
    host_block_size: int
    allocation_unit: int  # sectors per cluster
    num_dir_entries: int
    volume_start_sector: int  # absolute sector address of this label
    assignments: list[DriveAssignment]  # Configuration information

    @classmethod
    def from_bytes(cls, data: bytes, volume_start_sector: int) -> 'VirtualVolumeLabel':
        """Parse virtual volume label."""
        if len(data) < 64:
            raise HardDiskLabelError("Insufficient data for virtual volume label")

        label_type = struct.unpack_from('<H', data, VVL_LABEL_TYPE)[0]
        volume_name = data[VVL_VOLUME_NAME:VVL_VOLUME_NAME + 16].decode('ascii', errors='replace').strip('\x00')
        ipl_disk_address = struct.unpack_from('<I', data, VVL_IPL_DISK_ADDR)[0]
        ipl_load_address = struct.unpack_from('<H', data, VVL_IPL_DISK_ADDR + 4)[0]
        ipl_load_length = struct.unpack_from('<H', data, VVL_IPL_DISK_ADDR + 6)[0]
        ipl_code_entry = struct.unpack_from('<I', data, VVL_IPL_DISK_ADDR + 8)[0]
        volume_capacity = struct.unpack_from('<I', data, VVL_VOLUME_CAPACITY)[0]
        data_start = struct.unpack_from('<I', data, VVL_DATA_START)[0]
        host_block_size = struct.unpack_from('<H', data, VVL_HOST_BLOCK_SIZE)[0]
        allocation_unit = struct.unpack_from('<H', data, VVL_ALLOCATION_UNIT)[0]
        num_dir_entries = struct.unpack_from('<H', data, VVL_NUM_DIR_ENTRIES)[0]

        # Parse Configuration Information (after 16-byte reserved field)
        # Limit to reasonable max to avoid garbage data (max 16 assignments)
        assignments = []
        if len(data) > VVL_ASSIGNMENT_COUNT:
            assignment_count = min(data[VVL_ASSIGNMENT_COUNT], 16)
            offset = VVL_ASSIGNMENT_COUNT + 1
            for _ in range(assignment_count):
                if offset + 4 <= len(data):
                    device_unit = struct.unpack_from('<H', data, offset)[0]
                    volume_index = struct.unpack_from('<H', data, offset + 2)[0]
                    assignments.append(DriveAssignment(device_unit, volume_index))
                    offset += 4

        return cls(
            label_type=label_type,
            volume_name=volume_name,
            ipl_disk_address=ipl_disk_address,
            ipl_load_address=ipl_load_address,
            ipl_load_length=ipl_load_length,
            ipl_code_entry=ipl_code_entry,
            volume_capacity=volume_capacity,
            data_start=data_start,
            host_block_size=host_block_size,
            allocation_unit=allocation_unit,
            num_dir_entries=num_dir_entries,
            volume_start_sector=volume_start_sector,
            assignments=assignments
        )


@dataclass
class IBMPCBIOSParameterBlock:
    """BIOS Parameter Block for IBM PC FAT12 floppy disks."""
    oem_name: str
    bytes_per_sector: int       # 0x0B - always 512
    sectors_per_cluster: int    # 0x0D - 1 or 2 typically
    reserved_sectors: int       # 0x0E - usually 1
    num_fats: int               # 0x10 - usually 2
    root_entry_count: int       # 0x11 - 112 or 224
    total_sectors: int          # 0x13 or 0x20
    media_descriptor: int       # 0x15 - 0xF0 or 0xF9
    fat_sectors: int            # 0x16 - sectors per FAT
    sectors_per_track: int      # 0x18
    num_heads: int              # 0x1A
    # Calculated values
    fat_start: int = 0
    root_dir_start: int = 0
    root_dir_sectors: int = 0
    data_start: int = 0
    total_clusters: int = 0
    cluster_size: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> 'IBMPCBIOSParameterBlock':
        """Parse BPB from boot sector data."""
        if len(data) < 512:
            raise DiskError("Boot sector too small")

        # Check boot signature
        boot_sig = struct.unpack_from('<H', data, 0x1FE)[0]
        if boot_sig != 0xAA55:
            raise DiskError(f"Invalid boot signature: 0x{boot_sig:04X}")

        # Parse BPB fields
        oem_name = data[0x03:0x0B].decode('ascii', errors='replace').strip()
        bytes_per_sector = struct.unpack_from('<H', data, 0x0B)[0]
        sectors_per_cluster = data[0x0D]
        reserved_sectors = struct.unpack_from('<H', data, 0x0E)[0]
        num_fats = data[0x10]
        root_entry_count = struct.unpack_from('<H', data, 0x11)[0]
        total_sectors_16 = struct.unpack_from('<H', data, 0x13)[0]
        media_descriptor = data[0x15]
        fat_sectors = struct.unpack_from('<H', data, 0x16)[0]
        sectors_per_track = struct.unpack_from('<H', data, 0x18)[0]
        num_heads = struct.unpack_from('<H', data, 0x1A)[0]

        # Use TotalSectors16 unless it's 0 (then use TotalSectors32)
        if total_sectors_16 == 0:
            total_sectors = struct.unpack_from('<I', data, 0x20)[0]
        else:
            total_sectors = total_sectors_16

        # Validate BPB
        if bytes_per_sector != 512:
            raise DiskError(f"Unsupported bytes per sector: {bytes_per_sector}")
        if sectors_per_cluster not in (1, 2, 4, 8):
            raise DiskError(f"Invalid sectors per cluster: {sectors_per_cluster}")
        if num_fats == 0:
            raise DiskError("NumFATs cannot be zero")
        if fat_sectors == 0:
            raise DiskError("FATSize16 cannot be zero")

        # Calculate derived values
        fat_start = reserved_sectors
        root_dir_start = fat_start + (num_fats * fat_sectors)
        root_dir_sectors = (root_entry_count * 32 + 511) // 512
        data_start = root_dir_start + root_dir_sectors
        data_sectors = total_sectors - data_start
        total_clusters = data_sectors // sectors_per_cluster
        cluster_size = bytes_per_sector * sectors_per_cluster

        return cls(
            oem_name=oem_name,
            bytes_per_sector=bytes_per_sector,
            sectors_per_cluster=sectors_per_cluster,
            reserved_sectors=reserved_sectors,
            num_fats=num_fats,
            root_entry_count=root_entry_count,
            total_sectors=total_sectors,
            media_descriptor=media_descriptor,
            fat_sectors=fat_sectors,
            sectors_per_track=sectors_per_track,
            num_heads=num_heads,
            fat_start=fat_start,
            root_dir_start=root_dir_start,
            root_dir_sectors=root_dir_sectors,
            data_start=data_start,
            total_clusters=total_clusters,
            cluster_size=cluster_size
        )
