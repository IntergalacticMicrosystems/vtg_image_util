"""
Victor 9000 CP/M-86 disk image handler.

Supports reading, writing, and deleting files on Victor 9000 CP/M-86 floppy disks.
"""

from dataclasses import dataclass
from pathlib import Path

from .constants import (
    CPM_BLOCKS_PER_EXTENT,
    CPM_BLOCK_SIZE,
    CPM_DATA_START_SECTOR,
    CPM_DELETED,
    CPM_DIR_ENTRY_SIZE,
    CPM_DIR_INTERLEAVE,
    CPM_DIR_SECTORS,
    CPM_DIR_START_SECTOR,
    CPM_MAX_BLOCKS,
    CPM_RECORD_SIZE,
    CPM_RECORDS_PER_EXTENT,
    CPM_SECTOR_SIZE,
    CPM_SECTORS_PER_BLOCK,
    SECTOR_SIZE,
)
from .exceptions import (
    DiskError,
    DiskFullError,
    DirectoryFullError,
    FileNotFoundError,
    InvalidFilenameError,
)
from .models import CPMDirectoryEntry
from .utils import has_wildcards, match_filename, validate_filename


@dataclass
class CPMFileInfo:
    """Aggregated information about a CP/M file (may span multiple extents)."""
    user: int
    filename: str
    extension: str
    file_size: int
    extents: list[CPMDirectoryEntry]
    is_read_only: bool = False
    is_system: bool = False

    @property
    def full_name(self) -> str:
        if self.extension:
            return f"{self.filename}.{self.extension}"
        return self.filename

    @property
    def is_directory(self) -> bool:
        """CP/M doesn't have directories."""
        return False


class V9KCPMDiskImage:
    """Victor 9000 CP/M-86 floppy disk image handler."""

    # Disk geometry constants (defaults, may be overridden per-disk)
    SECTOR_SIZE = CPM_SECTOR_SIZE
    BLOCK_SIZE = CPM_BLOCK_SIZE
    SECTORS_PER_BLOCK = CPM_SECTORS_PER_BLOCK
    DIR_SECTORS = CPM_DIR_SECTORS
    DIR_INTERLEAVE = CPM_DIR_INTERLEAVE
    DATA_START_SECTOR = CPM_DATA_START_SECTOR

    def __init__(self, path: str, readonly: bool = True):
        """Open a CP/M disk image."""
        self.path = path
        self.readonly = readonly
        self._dirty = False

        mode = 'rb' if readonly else 'r+b'
        try:
            self._file = open(path, mode)
        except OSError as e:
            # Note: the builtin FileNotFoundError is an OSError; the custom
            # FileNotFoundError imported above is for in-image lookups only.
            raise DiskError(f"Cannot open disk image: {path}: {e}") from e

        try:
            # Media capacity in sectors/blocks, so writes never extend the image
            self._file.seek(0, 2)
            self._total_sectors = self._file.tell() // self.SECTOR_SIZE
            data_sectors = max(0, self._total_sectors - self.DATA_START_SECTOR)
            self._max_blocks = min(
                CPM_MAX_BLOCKS, data_sectors // self.SECTORS_PER_BLOCK
            )

            # Auto-detect directory start sector (some disks use 76, others 94)
            self.dir_start_sector = self._detect_dir_sector()
        except Exception:
            self._file.close()
            self._file = None
            raise

        # Load directory
        self._dir_cache: list[CPMDirectoryEntry] | None = None

    def _detect_dir_sector(self) -> int:
        """Detect the directory start sector for this disk."""
        self._file.seek(0)
        data = self._file.read()

        for sector in [76, 94, 1]:
            offset = sector * SECTOR_SIZE
            if offset + SECTOR_SIZE > len(data):
                continue

            valid = 0
            for i in range(4):
                entry = data[offset + i * 32:offset + (i + 1) * 32]
                if len(entry) < 32:
                    break
                user = entry[0]
                if user <= 15 or user == 0xE5:
                    name_bytes = entry[1:9]
                    try:
                        name = bytes([b & 0x7F for b in name_bytes]).decode('ascii')
                        if all(32 <= ord(c) < 127 for c in name):
                            valid += 1
                    except (UnicodeDecodeError, ValueError):
                        continue
            if valid >= 2:
                return sector

        # Default to 76 if no valid directory found
        return CPM_DIR_START_SECTOR

    def close(self) -> None:
        """Close the disk image."""
        if self._dirty and not self.readonly:
            self.flush()
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def flush(self) -> None:
        """Flush any pending writes."""
        if self._file and self._dirty:
            self._file.flush()
            self._dirty = False

    # -------------------------------------------------------------------------
    # Sector I/O
    # -------------------------------------------------------------------------

    def read_sector(self, sector: int) -> bytes:
        """Read a single 512-byte sector."""
        self._file.seek(sector * self.SECTOR_SIZE)
        data = self._file.read(self.SECTOR_SIZE)
        if len(data) < self.SECTOR_SIZE:
            raise DiskError(f"Failed to read sector {sector}")
        return data

    def write_sector(self, sector: int, data: bytes) -> None:
        """Write a single 512-byte sector."""
        if self.readonly:
            raise DiskError("Disk is read-only")
        if len(data) != self.SECTOR_SIZE:
            raise DiskError(f"Sector data must be {self.SECTOR_SIZE} bytes")
        # Never grow the image: a write past the end means corrupt geometry
        if sector < 0 or sector >= self._total_sectors:
            raise DiskError(
                f"Sector {sector} is outside the disk image "
                f"(0-{self._total_sectors - 1})"
            )
        self._file.seek(sector * self.SECTOR_SIZE)
        self._file.write(data)
        self._dirty = True

    # -------------------------------------------------------------------------
    # Block I/O
    # -------------------------------------------------------------------------

    def block_to_sector(self, block: int) -> int:
        """Convert allocation block number to sector number."""
        return self.DATA_START_SECTOR + (block * self.SECTORS_PER_BLOCK)

    def read_block(self, block: int) -> bytes:
        """Read a single allocation block (1024 bytes = 2 sectors)."""
        sector = self.block_to_sector(block)
        data = bytearray()
        for i in range(self.SECTORS_PER_BLOCK):
            data.extend(self.read_sector(sector + i))
        return bytes(data)

    def write_block(self, block: int, data: bytes) -> None:
        """Write a single allocation block (1024 bytes = 2 sectors)."""
        if len(data) != self.BLOCK_SIZE:
            raise DiskError(f"Block data must be {self.BLOCK_SIZE} bytes")
        sector = self.block_to_sector(block)
        for i in range(self.SECTORS_PER_BLOCK):
            offset = i * self.SECTOR_SIZE
            self.write_sector(sector + i, data[offset:offset + self.SECTOR_SIZE])

    # -------------------------------------------------------------------------
    # Directory operations
    # -------------------------------------------------------------------------

    def read_directory(self) -> list[CPMDirectoryEntry]:
        """Read all directory entries from the disk."""
        if self._dir_cache is not None:
            return self._dir_cache

        entries = []
        # Read directory sectors (interleaved - every 2nd sector)
        for sector_offset in range(self.DIR_SECTORS):
            sector = self.dir_start_sector + (sector_offset * self.DIR_INTERLEAVE)
            try:
                data = self.read_sector(sector)
            except DiskError:
                continue

            # Parse 16 entries per sector (32 bytes each)
            for i in range(16):
                entry_data = data[i * CPM_DIR_ENTRY_SIZE:(i + 1) * CPM_DIR_ENTRY_SIZE]
                if len(entry_data) < CPM_DIR_ENTRY_SIZE:
                    continue

                # Skip deleted entries (0xE5 in first byte)
                # Note: 0x00 is a valid user number (user 0), not an empty marker
                if entry_data[0] == CPM_DELETED:
                    continue

                # Skip entries with invalid user numbers (valid: 0-15)
                if entry_data[0] > 15:
                    continue

                try:
                    entry = CPMDirectoryEntry.from_bytes(entry_data)
                    # Skip entries with empty or all-space filenames
                    if not entry.filename.strip():
                        continue
                    # Skip entries with non-printable characters in filename
                    full_name = entry.filename + entry.extension
                    if not all(32 <= ord(c) < 127 for c in full_name):
                        continue
                    entries.append(entry)
                except DiskError:
                    continue

        self._dir_cache = entries
        return entries

    def _invalidate_dir_cache(self) -> None:
        """Invalidate the directory cache."""
        self._dir_cache = None

    def _find_free_dir_slot(self) -> tuple[int, int]:
        """Find a free directory entry slot. Returns (sector, entry_index)."""
        for sector_offset in range(self.DIR_SECTORS):
            sector = self.dir_start_sector + (sector_offset * self.DIR_INTERLEAVE)
            try:
                data = self.read_sector(sector)
            except DiskError:
                continue

            for i in range(16):
                entry_data = data[i * CPM_DIR_ENTRY_SIZE:(i + 1) * CPM_DIR_ENTRY_SIZE]
                # Free if deleted (0xE5). A 0x00 user byte is user 0 — a real
                # file — so only an entirely blank entry counts as never-used.
                if entry_data[0] == CPM_DELETED:
                    return (sector, i)
                if entry_data[0] == 0x00 and not any(entry_data):
                    return (sector, i)

        raise DirectoryFullError("No free directory entries")

    def _count_free_dir_slots(self) -> int:
        """Count free directory entry slots."""
        count = 0
        for sector_offset in range(self.DIR_SECTORS):
            sector = self.dir_start_sector + (sector_offset * self.DIR_INTERLEAVE)
            try:
                data = self.read_sector(sector)
            except DiskError:
                continue

            for i in range(16):
                entry_data = data[i * CPM_DIR_ENTRY_SIZE:(i + 1) * CPM_DIR_ENTRY_SIZE]
                if entry_data[0] == CPM_DELETED:
                    count += 1
                elif entry_data[0] == 0x00 and not any(entry_data):
                    count += 1
        return count

    def _write_dir_entry(self, sector: int, index: int, entry: CPMDirectoryEntry) -> None:
        """Write a directory entry at the specified location."""
        data = bytearray(self.read_sector(sector))
        entry_bytes = entry.to_bytes()
        offset = index * CPM_DIR_ENTRY_SIZE
        data[offset:offset + CPM_DIR_ENTRY_SIZE] = entry_bytes
        self.write_sector(sector, bytes(data))
        self._invalidate_dir_cache()

    # -------------------------------------------------------------------------
    # Block allocation
    # -------------------------------------------------------------------------

    def _get_used_blocks(self) -> set[int]:
        """Get set of all allocated block numbers."""
        used = set()
        for entry in self.read_directory():
            if not entry.is_deleted:
                used.update(entry.blocks)
        return used

    def _free_block_numbers(self, exclude_used: set[int] | None = None) -> list[int]:
        """
        List free allocation blocks on the actual media.

        Block 0 is never allocatable: a 0 in an extent's block list means
        "unused pointer", so a file cannot reference block 0.
        """
        used = exclude_used if exclude_used is not None else self._get_used_blocks()
        return [b for b in range(1, self._max_blocks) if b not in used]

    def _find_free_block(self) -> int:
        """Find a free allocation block."""
        free = self._free_block_numbers()
        if not free:
            raise DiskFullError("No free blocks on disk")
        return free[0]

    def _allocate_blocks(self, count: int) -> list[int]:
        """Allocate the specified number of blocks."""
        free = self._free_block_numbers()
        if len(free) < count:
            raise DiskFullError(f"Need {count} blocks, only {len(free)} available")
        return free[:count]

    # -------------------------------------------------------------------------
    # File operations (read)
    # -------------------------------------------------------------------------

    def list_files(self, path: list[str] | None = None) -> list[CPMFileInfo]:
        """List files in the directory.

        CP/M doesn't have subdirectories, so path is ignored.
        Returns aggregated file info (combining extents).
        """
        # Group entries by user + filename + extension
        files: dict[tuple, list[CPMDirectoryEntry]] = {}

        for entry in self.read_directory():
            if entry.is_deleted:
                continue

            key = (entry.user, entry.filename.upper(), entry.extension.upper())
            if key not in files:
                files[key] = []
            files[key].append(entry)

        # Build CPMFileInfo for each unique file
        result = []
        for (user, filename, ext), extents in files.items():
            # Sort extents by extent number
            extents.sort(key=lambda e: e.extent)

            # Calculate total file size
            # Last extent uses record_count, others are full (128 records)
            total_size = 0
            for i, extent in enumerate(extents):
                if i < len(extents) - 1:
                    # Not the last extent - assume full
                    total_size += CPM_RECORDS_PER_EXTENT * CPM_RECORD_SIZE
                else:
                    # Last extent - use actual record count
                    total_size += extent.record_count * CPM_RECORD_SIZE

            # Get attributes from first extent
            first = extents[0]
            result.append(CPMFileInfo(
                user=user,
                filename=filename.rstrip(),
                extension=ext.rstrip(),
                file_size=total_size,
                extents=extents,
                is_read_only=first.is_read_only,
                is_system=first.is_system
            ))

        # Sort by filename
        result.sort(key=lambda f: (f.user, f.full_name))
        return result

    def find_file(self, filename: str, user: int | None = None) -> CPMFileInfo | None:
        """Find a file by name. Optionally filter by user number."""
        try:
            name, ext = validate_filename(filename)
        except InvalidFilenameError:
            return None

        name = name.rstrip().upper()
        ext = ext.rstrip().upper()

        for f in self.list_files():
            if f.filename.upper() == name and f.extension.upper() == ext:
                if user is None or f.user == user:
                    return f
        return None

    def read_file(self, path: list[str]) -> bytes:
        """Read a file by path. CP/M doesn't have subdirectories."""
        if not path:
            raise FileNotFoundError("No filename specified")

        filename = path[-1]  # Use last component as filename
        file_info = self.find_file(filename)
        if not file_info:
            raise FileNotFoundError(f"File not found: {filename}")

        # Read data from all extents in order
        data = bytearray()
        for extent in file_info.extents:
            for block in extent.blocks:
                data.extend(self.read_block(block))

        # Trim to actual file size
        return bytes(data[:file_info.file_size])

    def find_matching_files(
        self, path: list[str], recursive: bool = False
    ) -> list[tuple[str, CPMFileInfo]]:
        """Find files matching a pattern. Returns list of (relative_path, file_info).

        CP/M doesn't have subdirectories, so recursive is ignored.
        """
        if not path:
            return []

        pattern = path[-1]  # Last component is the pattern

        results = []
        for file_info in self.list_files():
            if has_wildcards(pattern):
                if match_filename(pattern, file_info.full_name):
                    results.append((file_info.full_name, file_info))
            else:
                if file_info.full_name.upper() == pattern.upper():
                    results.append((file_info.full_name, file_info))

        return results

    # -------------------------------------------------------------------------
    # File operations (write)
    # -------------------------------------------------------------------------

    def write_file(self, path: list[str], data: bytes, user: int = 0) -> None:
        """Write a file to the disk."""
        if self.readonly:
            raise DiskError("Disk is read-only")

        if not path:
            raise InvalidFilenameError("No filename specified")

        filename = path[-1]
        name, ext = validate_filename(filename)

        # Calculate required blocks (an empty file needs none)
        num_blocks = (len(data) + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE

        # Check the new file fits BEFORE deleting an existing version, so a
        # failed overwrite never destroys the original file. Blocks and
        # directory slots freed by the deletion count as available.
        existing = self.find_file(filename)
        existing_blocks: set[int] = set()
        existing_extents = 0
        if existing:
            for extent in existing.extents:
                existing_blocks.update(extent.blocks)
            existing_extents = len(existing.extents)

        used = self._get_used_blocks() - existing_blocks
        free = self._free_block_numbers(exclude_used=used)
        if len(free) < num_blocks:
            raise DiskFullError(f"Need {num_blocks} blocks, only {len(free)} available")

        num_extents = max(1, (num_blocks + CPM_BLOCKS_PER_EXTENT - 1) // CPM_BLOCKS_PER_EXTENT)
        if self._count_free_dir_slots() + existing_extents < num_extents:
            raise DirectoryFullError("No free directory entries")

        if existing:
            self.delete_file(path)

        blocks = free[:num_blocks]

        # Write data to blocks
        for i, block in enumerate(blocks):
            offset = i * self.BLOCK_SIZE
            block_data = data[offset:offset + self.BLOCK_SIZE]
            if len(block_data) < self.BLOCK_SIZE:
                # Pad last block with 0x1A (CP/M EOF marker) or zeros
                block_data = block_data + bytes([0x1A] * (self.BLOCK_SIZE - len(block_data)))
            self.write_block(block, block_data)

        # Create directory entries (one per extent)
        # Each extent can hold 8 blocks (16-bit pointers) and 128 records (16KB)
        records_remaining = (len(data) + CPM_RECORD_SIZE - 1) // CPM_RECORD_SIZE

        extent_num = 0
        block_idx = 0

        # An empty file still needs one directory entry (0 records, no blocks)
        while block_idx < len(blocks) or extent_num == 0:
            # Find free directory slot
            sector, slot_idx = self._find_free_dir_slot()

            # How many blocks for this extent (max 8 with 16-bit pointers)
            extent_blocks = blocks[block_idx:block_idx + CPM_BLOCKS_PER_EXTENT]

            # How many records in this extent
            if records_remaining > CPM_RECORDS_PER_EXTENT:
                extent_records = CPM_RECORDS_PER_EXTENT
            else:
                extent_records = records_remaining

            # Create directory entry
            entry = CPMDirectoryEntry(
                user=user,
                filename=name.rstrip(),
                extension=ext.rstrip(),
                extent=extent_num,
                record_count=extent_records,
                blocks=extent_blocks,
                is_deleted=False
            )

            self._write_dir_entry(sector, slot_idx, entry)

            block_idx += max(1, len(extent_blocks))
            records_remaining -= extent_records
            extent_num += 1

        self._invalidate_dir_cache()

    def delete_file(self, path: list[str]) -> None:
        """Delete a file from the disk."""
        if self.readonly:
            raise DiskError("Disk is read-only")

        if not path:
            raise FileNotFoundError("No filename specified")

        filename = path[-1]
        file_info = self.find_file(filename)
        if not file_info:
            raise FileNotFoundError(f"File not found: {filename}")

        # Mark all extents as deleted
        for extent in file_info.extents:
            # Find this extent in the directory and mark as deleted
            for sector_offset in range(self.DIR_SECTORS):
                sector = self.dir_start_sector + (sector_offset * self.DIR_INTERLEAVE)
                try:
                    data = bytearray(self.read_sector(sector))
                except DiskError:
                    continue

                for i in range(16):
                    entry_data = data[i * CPM_DIR_ENTRY_SIZE:(i + 1) * CPM_DIR_ENTRY_SIZE]
                    # Skip deleted and never-used slots. A 0x00 user byte with
                    # any other content is a real user-0 file — do not skip it,
                    # or user-0 files become undeletable.
                    if entry_data[0] == CPM_DELETED:
                        continue
                    if entry_data[0] == 0x00 and not any(entry_data):
                        continue

                    # Check if this is the extent we're looking for
                    try:
                        dir_entry = CPMDirectoryEntry.from_bytes(entry_data)
                    except DiskError:
                        continue

                    if (dir_entry.user == extent.user and
                        dir_entry.filename.upper() == extent.filename.upper() and
                        dir_entry.extension.upper() == extent.extension.upper() and
                        dir_entry.extent == extent.extent):
                        # Mark as deleted
                        data[i * CPM_DIR_ENTRY_SIZE] = CPM_DELETED
                        self.write_sector(sector, bytes(data))
                        break

        self._invalidate_dir_cache()
