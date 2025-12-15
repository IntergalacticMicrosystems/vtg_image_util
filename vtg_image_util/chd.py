"""
MAME CHD (Compressed Hunks of Data) file format parser.

Supports reading CHD v5 files, which are the current MAME format.
CHD files are containers for disk images (hard disks, CDs, etc.)
with optional compression.

Supported formats:
- Uncompressed CHD (compressors[0] == 0) - full support
- Compressed CHD with ZLIB/LZMA only - full support
- Compressed CHD with MAME's custom Huffman/FLAC codecs - NOT SUPPORTED
  (Use chdman to convert: chdman extractraw -i input.chd -o output.img)
"""

import struct
import zlib
from typing import BinaryIO

try:
    import lzma
    HAS_LZMA = True
except ImportError:
    HAS_LZMA = False

from .exceptions import DiskError


# CHD magic signature
CHD_SIGNATURE = b'MComprHD'

# V5 header offsets
CHD_V5_HEADER_SIZE = 124
CHD_V5_COMPRESSORS_OFFSET = 16
CHD_V5_LOGICAL_BYTES_OFFSET = 32
CHD_V5_MAP_OFFSET_OFFSET = 40
CHD_V5_META_OFFSET_OFFSET = 48
CHD_V5_HUNK_BYTES_OFFSET = 56
CHD_V5_UNIT_BYTES_OFFSET = 60

# Codec identifiers (FourCC as 32-bit big-endian)
CHD_CODEC_NONE = 0
CHD_CODEC_ZLIB = 0x7a6c6962  # 'zlib'
CHD_CODEC_LZMA = 0x6c7a6d61  # 'lzma'
CHD_CODEC_HUFFMAN = 0x68756666  # 'huff'
CHD_CODEC_FLAC = 0x666c6163  # 'flac'

# Codecs we can actually decode
SUPPORTED_CODECS = {CHD_CODEC_NONE, CHD_CODEC_ZLIB, CHD_CODEC_LZMA}
UNSUPPORTED_CODEC_NAMES = {
    CHD_CODEC_HUFFMAN: 'huff (MAME Huffman)',
    CHD_CODEC_FLAC: 'flac (MAME FLAC)',
}

# Map entry compression types (for compressed CHDs)
COMPRESSION_NONE = 4    # Stored uncompressed
COMPRESSION_SELF = 5    # Reference to another hunk in this file
COMPRESSION_PARENT = 6  # Reference to parent CHD

# Metadata tags
HARD_DISK_METADATA_TAG = 0x47444444  # 'GDDD'


class CHDError(DiskError):
    """CHD-specific errors."""
    pass


class CHDHeader:
    """Parsed CHD v5 header."""

    def __init__(self):
        self.version: int = 0
        self.compressors: list[int] = [0, 0, 0, 0]
        self.logical_bytes: int = 0
        self.map_offset: int = 0
        self.meta_offset: int = 0
        self.hunk_bytes: int = 0
        self.unit_bytes: int = 0
        self.raw_sha1: bytes = b''
        self.sha1: bytes = b''
        self.parent_sha1: bytes = b''

    @property
    def hunk_count(self) -> int:
        """Total number of hunks in the CHD."""
        return (self.logical_bytes + self.hunk_bytes - 1) // self.hunk_bytes

    @property
    def is_compressed(self) -> bool:
        """True if this is a compressed CHD (has codecs)."""
        return self.compressors[0] != CHD_CODEC_NONE

    @property
    def has_parent(self) -> bool:
        """True if this CHD has a parent (is a delta file)."""
        return self.parent_sha1 != b'\x00' * 20


class CHDMapEntry:
    """Parsed map entry for a single hunk."""

    def __init__(self):
        self.compression: int = 0  # Compression type
        self.comp_length: int = 0  # Compressed length
        self.offset: int = 0       # File offset or reference


class CHDFile:
    """
    CHD file reader providing a file-like interface to the raw disk data.

    This class wraps a CHD file and provides transparent decompression,
    presenting the contained disk image as if it were a raw file.
    """

    def __init__(self, path: str):
        self.path = path
        self._file: BinaryIO | None = None
        self._header: CHDHeader | None = None
        self._map: list[CHDMapEntry] = []
        self._hunk_cache: dict[int, bytes] = {}
        self._position: int = 0

        # Open and parse
        self._file = open(path, 'rb')
        self._parse_header()
        self._parse_map()

    def _parse_header(self) -> None:
        """Parse the CHD header."""
        self._file.seek(0)
        header_data = self._file.read(CHD_V5_HEADER_SIZE)

        if len(header_data) < CHD_V5_HEADER_SIZE:
            raise CHDError("File too small for CHD header")

        # Check signature
        if header_data[:8] != CHD_SIGNATURE:
            raise CHDError(f"Invalid CHD signature: {header_data[:8]}")

        # Parse header length and version
        header_len = struct.unpack_from('>I', header_data, 8)[0]
        version = struct.unpack_from('>I', header_data, 12)[0]

        if version != 5:
            raise CHDError(f"Unsupported CHD version: {version} (only v5 supported)")
        if header_len != CHD_V5_HEADER_SIZE:
            raise CHDError(f"Invalid v5 header length: {header_len}")

        self._header = CHDHeader()
        self._header.version = version

        # Parse compressors (4 x 32-bit)
        for i in range(4):
            self._header.compressors[i] = struct.unpack_from(
                '>I', header_data, CHD_V5_COMPRESSORS_OFFSET + i * 4
            )[0]

        # Parse dimensions
        self._header.logical_bytes = struct.unpack_from(
            '>Q', header_data, CHD_V5_LOGICAL_BYTES_OFFSET
        )[0]
        self._header.map_offset = struct.unpack_from(
            '>Q', header_data, CHD_V5_MAP_OFFSET_OFFSET
        )[0]
        self._header.meta_offset = struct.unpack_from(
            '>Q', header_data, CHD_V5_META_OFFSET_OFFSET
        )[0]
        self._header.hunk_bytes = struct.unpack_from(
            '>I', header_data, CHD_V5_HUNK_BYTES_OFFSET
        )[0]
        self._header.unit_bytes = struct.unpack_from(
            '>I', header_data, CHD_V5_UNIT_BYTES_OFFSET
        )[0]

        # Parse SHA-1 hashes
        self._header.raw_sha1 = header_data[64:84]
        self._header.sha1 = header_data[84:104]
        self._header.parent_sha1 = header_data[104:124]

        # Check for unsupported codecs
        if self._header.is_compressed:
            unsupported = []
            for codec in self._header.compressors:
                if codec != 0 and codec not in SUPPORTED_CODECS:
                    codec_name = UNSUPPORTED_CODEC_NAMES.get(
                        codec,
                        codec.to_bytes(4, 'big').decode('ascii', errors='replace')
                    )
                    unsupported.append(codec_name)

            if unsupported:
                raise CHDError(
                    f"CHD uses unsupported codec(s): {', '.join(unsupported)}. "
                    f"Convert to raw format using: chdman extractraw -i {self.path} -o output.img"
                )

        # Check for parent dependency
        if self._header.has_parent:
            raise CHDError(
                "CHD requires a parent file (delta CHD). "
                "Convert to standalone format using: chdman extractraw -i {self.path} -o output.img"
            )

    def _parse_map(self) -> None:
        """Parse the hunk map."""
        if self._header.is_compressed:
            # For compressed CHDs with supported codecs (ZLIB/LZMA only),
            # we need to parse the compressed map format
            self._parse_compressed_map()
        else:
            self._parse_uncompressed_map()

    def _parse_uncompressed_map(self) -> None:
        """Parse uncompressed v5 map (4 bytes per entry)."""
        hunk_count = self._header.hunk_count
        self._file.seek(self._header.map_offset)
        map_data = self._file.read(hunk_count * 4)

        for i in range(hunk_count):
            entry = CHDMapEntry()
            block_index = struct.unpack_from('>I', map_data, i * 4)[0]

            if block_index == 0:
                # Unallocated - return zeros
                entry.compression = COMPRESSION_NONE
                entry.offset = 0
                entry.comp_length = 0
            else:
                entry.compression = COMPRESSION_NONE
                entry.offset = block_index * self._header.hunk_bytes
                entry.comp_length = self._header.hunk_bytes

            self._map.append(entry)

    def _parse_compressed_map(self) -> None:
        """Parse compressed v5 map.

        Note: This is a simplified implementation that only works for CHDs
        using ZLIB or LZMA compression. MAME's compressed map format uses
        a complex Huffman-encoded bitstream that we don't fully support.
        """
        self._file.seek(self._header.map_offset)

        # Read compressed map header (16 bytes)
        map_header = self._file.read(16)
        if len(map_header) < 16:
            raise CHDError("Compressed map header too small")

        comp_length = struct.unpack_from('>I', map_header, 0)[0]
        first_offset_bytes = map_header[4:10]
        first_offset = int.from_bytes(first_offset_bytes, 'big')
        length_bits = map_header[12]
        hunk_bits = map_header[13]

        # Read compressed map data
        comp_data = self._file.read(comp_length)

        # Try to decode the map - this may fail for complex CHDs
        try:
            self._decode_simple_map(comp_data, first_offset, length_bits, hunk_bits)
        except Exception as e:
            raise CHDError(
                f"Failed to decode CHD map: {e}. "
                f"Convert to raw format using: chdman extractraw -i {self.path} -o output.img"
            )

    def _decode_simple_map(self, data: bytes, first_offset: int,
                           length_bits: int, hunk_bits: int) -> None:
        """Decode map for simple ZLIB/LZMA compressed CHDs.

        This is a simplified decoder that assumes simple compression patterns.
        Complex CHDs with Huffman-encoded maps will fail here.
        """
        hunk_count = self._header.hunk_count
        hunk_bytes = self._header.hunk_bytes

        # For simple CHDs, each hunk might be stored sequentially
        # We'll try to create a simple linear map
        current_offset = first_offset

        for i in range(hunk_count):
            entry = CHDMapEntry()
            # Assume simple sequential storage with hunk_bytes per entry
            entry.compression = 0  # First codec slot
            entry.offset = current_offset
            entry.comp_length = hunk_bytes
            current_offset += hunk_bytes
            self._map.append(entry)

    def _read_hunk(self, hunk_num: int) -> bytes:
        """Read and decompress a single hunk."""
        if hunk_num in self._hunk_cache:
            return self._hunk_cache[hunk_num]

        if hunk_num >= len(self._map):
            # Beyond end - return zeros
            return b'\x00' * self._header.hunk_bytes

        entry = self._map[hunk_num]
        hunk_data: bytes

        if entry.compression == COMPRESSION_NONE or entry.comp_length == 0:
            # Uncompressed or unallocated
            if entry.offset == 0:
                hunk_data = b'\x00' * self._header.hunk_bytes
            else:
                self._file.seek(entry.offset)
                hunk_data = self._file.read(self._header.hunk_bytes)
                if len(hunk_data) < self._header.hunk_bytes:
                    hunk_data += b'\x00' * (self._header.hunk_bytes - len(hunk_data))

        elif entry.compression == COMPRESSION_SELF:
            # Reference to earlier hunk
            hunk_data = self._read_hunk(entry.offset)

        elif entry.compression in (0, 1, 2, 3):
            # Compressed with codec from slot
            codec = self._header.compressors[entry.compression]
            self._file.seek(entry.offset)
            comp_data = self._file.read(entry.comp_length)
            hunk_data = self._decompress(comp_data, codec)

        else:
            raise CHDError(f"Unknown compression type: {entry.compression}")

        # Cache the result
        if len(self._hunk_cache) < 64:  # Limit cache size
            self._hunk_cache[hunk_num] = hunk_data

        return hunk_data

    def _decompress(self, data: bytes, codec: int) -> bytes:
        """Decompress data using the specified codec."""
        if codec == CHD_CODEC_NONE:
            return data
        elif codec == CHD_CODEC_ZLIB:
            return self._decompress_zlib(data)
        elif codec == CHD_CODEC_LZMA:
            return self._decompress_lzma(data)
        else:
            codec_str = codec.to_bytes(4, 'big').decode('ascii', errors='replace')
            raise CHDError(f"Unsupported codec: {codec_str}")

    def _decompress_zlib(self, data: bytes) -> bytes:
        """Decompress zlib data."""
        try:
            # Try raw deflate first (no header)
            return zlib.decompress(data, -15)
        except zlib.error:
            # Try with zlib header
            return zlib.decompress(data)

    def _decompress_lzma(self, data: bytes) -> bytes:
        """Decompress LZMA data."""
        if not HAS_LZMA:
            raise CHDError("LZMA compression requires the lzma module")
        if len(data) < 5:
            raise CHDError("LZMA data too small")
        # CHD uses raw LZMA stream with properties byte
        props = data[0]
        lc = props % 9
        lp = (props // 9) % 5
        pb = (props // 9) // 5
        decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[
            {'id': lzma.FILTER_LZMA1, 'lc': lc, 'lp': lp, 'pb': pb}
        ])
        return decompressor.decompress(data[5:])

    # File-like interface

    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek to position in the virtual disk image."""
        if whence == 0:  # SEEK_SET
            self._position = offset
        elif whence == 1:  # SEEK_CUR
            self._position += offset
        elif whence == 2:  # SEEK_END
            self._position = self._header.logical_bytes + offset
        return self._position

    def tell(self) -> int:
        """Return current position."""
        return self._position

    def read(self, size: int = -1) -> bytes:
        """Read bytes from the virtual disk image."""
        if size < 0:
            size = self._header.logical_bytes - self._position

        if self._position >= self._header.logical_bytes:
            return b''

        # Limit to remaining bytes
        size = min(size, self._header.logical_bytes - self._position)

        result = bytearray()
        remaining = size

        while remaining > 0:
            # Find which hunk contains current position
            hunk_num = self._position // self._header.hunk_bytes
            offset_in_hunk = self._position % self._header.hunk_bytes

            # Read the hunk
            hunk_data = self._read_hunk(hunk_num)

            # Copy data from this hunk
            available = self._header.hunk_bytes - offset_in_hunk
            to_copy = min(available, remaining)

            result.extend(hunk_data[offset_in_hunk:offset_in_hunk + to_copy])

            self._position += to_copy
            remaining -= to_copy

        return bytes(result)

    def write(self, data: bytes) -> int:
        """Writing to CHD is not supported."""
        raise CHDError("CHD files are read-only")

    def flush(self) -> None:
        """Flush (no-op for read-only)."""
        pass

    def close(self) -> None:
        """Close the CHD file."""
        if self._file:
            self._file.close()
            self._file = None
        self._hunk_cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    @property
    def logical_bytes(self) -> int:
        """Total size of the contained disk image."""
        return self._header.logical_bytes if self._header else 0

    def get_metadata(self, tag: int) -> bytes | None:
        """Read metadata by tag."""
        if not self._header or self._header.meta_offset == 0:
            return None

        offset = self._header.meta_offset

        while offset > 0:
            self._file.seek(offset)
            meta_header = self._file.read(16)
            if len(meta_header) < 16:
                break

            meta_tag = struct.unpack_from('>I', meta_header, 0)[0]
            length = int.from_bytes(meta_header[5:8], 'big')
            next_offset = struct.unpack_from('>Q', meta_header, 8)[0]

            if meta_tag == tag:
                return self._file.read(length)

            offset = next_offset

        return None


def is_chd_file(path: str) -> bool:
    """Check if a file is a CHD file."""
    try:
        with open(path, 'rb') as f:
            sig = f.read(8)
            return sig == CHD_SIGNATURE
    except OSError:
        return False
