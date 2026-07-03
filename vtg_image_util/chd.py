"""
MAME CHD (Compressed Hunks of Data) file format parser.

Supports reading CHD v5 files, which are the current MAME format.
CHD files are containers for disk images (hard disks, CDs, etc.)
with optional compression.

Supported formats:
- Uncompressed CHD - full support
- Compressed CHD with ZLIB, LZMA, or Huffman codecs - full support,
  including the Huffman-encoded v5 hunk map (verified against its CRC)
- FLAC-compressed hunks and parent (delta) CHDs - NOT SUPPORTED
  (Use chdman to convert: chdman extractraw -i input.chd -o output.img)

A CHD may list an unsupported codec in its header without using it; only
codecs actually referenced by the hunk map cause a CHDError.
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
SUPPORTED_CODECS = {
    CHD_CODEC_NONE, CHD_CODEC_ZLIB, CHD_CODEC_LZMA,
    CHD_CODEC_HUFFMAN, CHD_CODEC_FLAC,
}

# Map entry compression types (for compressed CHDs)
COMPRESSION_TYPE_0 = 0  # Codec slot 0..3
COMPRESSION_TYPE_3 = 3
COMPRESSION_NONE = 4    # Stored uncompressed
COMPRESSION_SELF = 5    # Reference to another hunk in this file
COMPRESSION_PARENT = 6  # Reference to parent CHD
# Pseudo-types used only inside the compressed map encoding
COMPRESSION_RLE_SMALL = 7
COMPRESSION_RLE_LARGE = 8
COMPRESSION_SELF_0 = 9
COMPRESSION_SELF_1 = 10
COMPRESSION_PARENT_SELF = 11
COMPRESSION_PARENT_0 = 12
COMPRESSION_PARENT_1 = 13

# Metadata tags
HARD_DISK_METADATA_TAG = 0x47444444  # 'GDDD'


class CHDError(DiskError):
    """CHD-specific errors."""
    pass


def _crc16(data: bytes) -> int:
    """CRC-16/CCITT (poly 0x1021, init 0xFFFF), as used by MAME."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class _BitReader:
    """MSB-first bit reader over a byte buffer (MAME bitstream_in)."""

    def __init__(self, data: bytes):
        self._data = data
        self._bitpos = 0

    def read(self, numbits: int) -> int:
        value = 0
        data = self._data
        pos = self._bitpos
        end = len(data) * 8
        for _ in range(numbits):
            if pos >= end:
                raise CHDError("Bitstream overflow while decoding CHD data")
            value = (value << 1) | ((data[pos >> 3] >> (7 - (pos & 7))) & 1)
            pos += 1
        self._bitpos = pos
        return value


class _HuffmanDecoder:
    """
    Canonical Huffman decoder matching MAME's huffman_context_base.

    Trees arrive either RLE-encoded (used for the map's compression codes)
    or Huffman-encoded via a small helper tree (used by the 'huff' codec).
    """

    def __init__(self, numcodes: int, maxbits: int):
        self.numcodes = numcodes
        self.maxbits = maxbits
        self.numbits = [0] * numcodes
        self._table: dict[tuple[int, int], int] = {}

    def import_tree_rle(self, bits: _BitReader) -> None:
        """Import an RLE-encoded tree (MAME import_tree_rle)."""
        if self.maxbits >= 16:
            entry_bits = 5
        elif self.maxbits >= 8:
            entry_bits = 4
        else:
            entry_bits = 3

        curnode = 0
        while curnode < self.numcodes:
            nodebits = bits.read(entry_bits)
            if nodebits != 1:
                self.numbits[curnode] = nodebits
                curnode += 1
            else:
                nodebits = bits.read(entry_bits)
                if nodebits == 1:
                    self.numbits[curnode] = nodebits
                    curnode += 1
                else:
                    repcount = bits.read(entry_bits) + 3
                    if curnode + repcount > self.numcodes:
                        raise CHDError("Invalid RLE Huffman tree in CHD")
                    for _ in range(repcount):
                        self.numbits[curnode] = nodebits
                        curnode += 1

        self._assign_canonical_codes()

    def import_tree_huffman(self, bits: _BitReader) -> None:
        """Import a Huffman-encoded tree (MAME import_tree_huffman)."""
        small = _HuffmanDecoder(24, 6)
        small.numbits[0] = bits.read(3)
        start = bits.read(3) + 1
        count = 0
        for index in range(1, 24):
            if index < start or count == 7:
                small.numbits[index] = 0
            else:
                count = bits.read(3)
                small.numbits[index] = 0 if count == 7 else count
        small._assign_canonical_codes()

        # Maximum length of an RLE count
        temp = self.numcodes - 9
        rlefullbits = 0
        while temp != 0:
            temp >>= 1
            rlefullbits += 1

        last = 0
        curcode = 0
        while curcode < self.numcodes:
            value = small.decode_one(bits)
            if value != 0:
                last = value - 1
                self.numbits[curcode] = last
                curcode += 1
            else:
                repcount = bits.read(3) + 2
                if repcount == 7 + 2:
                    repcount += bits.read(rlefullbits)
                while repcount != 0 and curcode < self.numcodes:
                    self.numbits[curcode] = last
                    curcode += 1
                    repcount -= 1

        self._assign_canonical_codes()

    def _assign_canonical_codes(self) -> None:
        """Assign canonical codes (MAME assign_canonical_codes)."""
        bithisto = [0] * 33
        for curcode in range(self.numcodes):
            length = self.numbits[curcode]
            if length > self.maxbits:
                raise CHDError("Huffman code length exceeds maximum")
            if length <= 32:
                bithisto[length] += 1

        curstart = 0
        for codelen in range(32, 0, -1):
            nextstart = (curstart + bithisto[codelen]) >> 1
            if codelen != 1 and nextstart * 2 != curstart + bithisto[codelen]:
                raise CHDError("Inconsistent Huffman tree in CHD")
            bithisto[codelen] = curstart
            curstart = nextstart

        self._table = {}
        for curcode in range(self.numcodes):
            length = self.numbits[curcode]
            if length > 0:
                self._table[(length, bithisto[length])] = curcode
                bithisto[length] += 1

    def decode_one(self, bits: _BitReader) -> int:
        """Decode a single symbol from the bitstream."""
        accum = 0
        for length in range(1, self.maxbits + 1):
            accum = (accum << 1) | bits.read(1)
            symbol = self._table.get((length, accum))
            if symbol is not None:
                return symbol
        raise CHDError("Invalid Huffman code in CHD data")


# FLAC fixed-predictor coefficients by order
_FLAC_FIXED_COEFFS = [
    [],
    [1],
    [2, -1],
    [3, -3, 1],
    [4, -6, 4, -1],
]


class _FlacFrameDecoder:
    """
    Minimal FLAC frame decoder for MAME's CHD 'flac' codec.

    MAME stores raw FLAC frames (no fLaC container): 16-bit samples,
    2 channels. Only the features libFLAC emits for that configuration
    are implemented: constant, verbatim, fixed and LPC subframes with
    partitioned Rice residuals, and all four stereo decorrelation modes.
    """

    _BLOCK_SIZES = [0, 192, 576, 1152, 2304, 4608, -1, -2,
                    256, 512, 1024, 2048, 4096, 8192, 16384, 32768]

    def __init__(self, data: bytes):
        self._bits = _BitReader(data)

    def _read_signed(self, numbits: int) -> int:
        value = self._bits.read(numbits)
        if value & (1 << (numbits - 1)):
            value -= 1 << numbits
        return value

    def _read_utf8_number(self) -> int:
        first = self._bits.read(8)
        if first < 0x80:
            return first
        ones = 0
        mask = 0x80
        while first & mask:
            ones += 1
            mask >>= 1
        value = first & (mask - 1)
        for _ in range(ones - 1):
            value = (value << 6) | (self._bits.read(8) & 0x3F)
        return value

    def decode_frame(self) -> list[int]:
        """Decode one frame; returns interleaved samples."""
        bits = self._bits

        # Frame header
        sync = bits.read(14)
        if sync != 0x3FFE:
            raise CHDError(f"Invalid FLAC frame sync: {sync:#x}")
        bits.read(1)  # reserved
        bits.read(1)  # blocking strategy
        block_size_code = bits.read(4)
        sample_rate_code = bits.read(4)
        channel_assignment = bits.read(4)
        sample_size_code = bits.read(3)
        bits.read(1)  # reserved
        self._read_utf8_number()  # frame number

        if block_size_code == 6:
            block_size = bits.read(8) + 1
        elif block_size_code == 7:
            block_size = bits.read(16) + 1
        else:
            block_size = self._BLOCK_SIZES[block_size_code]
            if block_size <= 0:
                raise CHDError("Invalid FLAC block size code")
        if sample_rate_code == 12:
            bits.read(8)
        elif sample_rate_code in (13, 14):
            bits.read(16)

        sample_sizes = {1: 8, 2: 12, 4: 16, 5: 20, 6: 24, 7: 32}
        bps = sample_sizes.get(sample_size_code)
        if bps is None:
            raise CHDError("Unsupported FLAC sample size")

        if channel_assignment <= 7:
            num_channels = channel_assignment + 1
        else:
            num_channels = 2
        if num_channels != 2:
            raise CHDError("Only 2-channel FLAC data is supported")

        bits.read(8)  # header CRC-8 (whole-hunk CRC catches corruption)

        # Subframes; side channels carry one extra bit
        channels = []
        for ch in range(2):
            ch_bps = bps
            if channel_assignment == 8 and ch == 1:
                ch_bps += 1
            elif channel_assignment == 9 and ch == 0:
                ch_bps += 1
            elif channel_assignment == 10 and ch == 1:
                ch_bps += 1
            channels.append(self._decode_subframe(block_size, ch_bps))

        # Undo stereo decorrelation
        left, right = channels
        if channel_assignment == 8:  # left/side
            right = [l - s for l, s in zip(left, right)]
        elif channel_assignment == 9:  # right/side
            left, right = [r + s for s, r in zip(left, right)], right
        elif channel_assignment == 10:  # mid/side
            mid, side = left, right
            left = []
            right = []
            for m, s in zip(mid, side):
                m = (m << 1) | (s & 1)
                left.append((m + s) >> 1)
                right.append((m - s) >> 1)

        # Frame footer: pad to byte boundary + CRC-16
        bits._bitpos = (bits._bitpos + 7) & ~7
        bits.read(16)

        samples = [0] * (block_size * 2)
        samples[0::2] = left
        samples[1::2] = right
        return samples

    def _decode_subframe(self, block_size: int, bps: int) -> list[int]:
        bits = self._bits
        if bits.read(1) != 0:
            raise CHDError("Invalid FLAC subframe padding")
        subframe_type = bits.read(6)
        wasted = 0
        if bits.read(1):
            wasted = 1
            while bits.read(1) == 0:
                wasted += 1
        bps -= wasted

        if subframe_type == 0:  # CONSTANT
            value = self._read_signed(bps)
            samples = [value] * block_size
        elif subframe_type == 1:  # VERBATIM
            samples = [self._read_signed(bps) for _ in range(block_size)]
        elif 8 <= subframe_type <= 12:  # FIXED, order 0-4
            order = subframe_type & 7
            samples = [self._read_signed(bps) for _ in range(order)]
            residuals = self._decode_residuals(block_size, order)
            coeffs = _FLAC_FIXED_COEFFS[order]
            for i in range(order, block_size):
                prediction = sum(
                    c * samples[i - 1 - j] for j, c in enumerate(coeffs))
                samples.append(prediction + residuals[i - order])
        elif subframe_type >= 32:  # LPC
            order = (subframe_type & 31) + 1
            samples = [self._read_signed(bps) for _ in range(order)]
            precision = bits.read(4) + 1
            if precision == 16:
                raise CHDError("Invalid FLAC LPC precision")
            shift = self._read_signed(5)
            coeffs = [self._read_signed(precision) for _ in range(order)]
            residuals = self._decode_residuals(block_size, order)
            for i in range(order, block_size):
                prediction = sum(
                    c * samples[i - 1 - j] for j, c in enumerate(coeffs))
                samples.append((prediction >> shift) + residuals[i - order])
        else:
            raise CHDError(f"Unsupported FLAC subframe type: {subframe_type}")

        if wasted:
            samples = [s << wasted for s in samples]
        return samples

    def _decode_residuals(self, block_size: int, order: int) -> list[int]:
        bits = self._bits
        method = bits.read(2)
        if method > 1:
            raise CHDError("Unsupported FLAC residual coding method")
        param_bits = 4 if method == 0 else 5
        escape = (1 << param_bits) - 1

        partition_order = bits.read(4)
        partitions = 1 << partition_order
        samples_per_partition = block_size >> partition_order

        residuals = []
        for p in range(partitions):
            count = samples_per_partition - (order if p == 0 else 0)
            param = bits.read(param_bits)
            if param == escape:
                raw_bits = bits.read(5)
                for _ in range(count):
                    residuals.append(
                        self._read_signed(raw_bits) if raw_bits else 0)
            else:
                for _ in range(count):
                    quotient = 0
                    while bits.read(1) == 0:
                        quotient += 1
                    unsigned = (quotient << param) | bits.read(param)
                    residuals.append((unsigned >> 1) ^ -(unsigned & 1))
        return residuals


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
        self.offset: int = 0       # File offset or hunk reference
        self.crc: int | None = None  # CRC-16 of decompressed hunk, if known


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
        try:
            self._parse_header()
            self._parse_map()
        except Exception:
            self._file.close()
            self._file = None
            raise

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

        # Note: codec support is checked against the codecs the hunk map
        # actually uses (in _parse_map), not the header's codec list — a CHD
        # may list a codec it never uses.

        # Check for parent dependency
        if self._header.has_parent:
            raise CHDError(
                f"CHD requires a parent file (delta CHD). "
                f"Convert to standalone format using: "
                f"chdman extractraw -i {self.path} -o output.img"
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
        """
        Parse the compressed v5 map (MAME chd_file::decompress_v5_map).

        The map is a Huffman-encoded bitstream: first the per-hunk
        compression types (with RLE escape codes), then per-hunk
        length/offset/CRC fields. A CRC-16 over the reconstructed map
        verifies the decode was bit-exact.
        """
        self._file.seek(self._header.map_offset)

        # Map header (16 bytes)
        map_header = self._file.read(16)
        if len(map_header) < 16:
            raise CHDError("Compressed map header too small")

        comp_length = struct.unpack_from('>I', map_header, 0)[0]
        first_offset = int.from_bytes(map_header[4:10], 'big')
        map_crc = struct.unpack_from('>H', map_header, 10)[0]
        length_bits = map_header[12]
        self_bits = map_header[13]
        parent_bits = map_header[14]

        comp_data = self._file.read(comp_length)
        if len(comp_data) < comp_length:
            raise CHDError("Compressed map data truncated")

        hunk_count = self._header.hunk_count
        hunk_bytes = self._header.hunk_bytes
        unit_bytes = self._header.unit_bytes
        bits = _BitReader(comp_data)

        # First, decode the compression type for each hunk
        decoder = _HuffmanDecoder(16, 8)
        decoder.import_tree_rle(bits)

        comp_types = []
        last_comp = 0
        rep_count = 0
        for _ in range(hunk_count):
            if rep_count > 0:
                comp_types.append(last_comp)
                rep_count -= 1
                continue
            val = decoder.decode_one(bits)
            if val == COMPRESSION_RLE_SMALL:
                comp_types.append(last_comp)
                rep_count = 2 + decoder.decode_one(bits)
            elif val == COMPRESSION_RLE_LARGE:
                comp_types.append(last_comp)
                rep_count = 2 + 16 + (decoder.decode_one(bits) << 4)
                rep_count += decoder.decode_one(bits)
            else:
                last_comp = val
                comp_types.append(val)

        # Then, extract length/offset/CRC for each hunk
        raw_map = bytearray(hunk_count * 12)
        cur_offset = first_offset
        last_self = 0
        last_parent = 0
        for hunknum in range(hunk_count):
            comp = comp_types[hunknum]
            offset = cur_offset
            length = 0
            crc = None

            if comp <= COMPRESSION_TYPE_3:
                length = bits.read(length_bits)
                cur_offset += length
                crc = bits.read(16)
            elif comp == COMPRESSION_NONE:
                length = hunk_bytes
                cur_offset += length
                crc = bits.read(16)
            elif comp == COMPRESSION_SELF:
                offset = bits.read(self_bits)
                last_self = offset
            elif comp == COMPRESSION_PARENT:
                offset = bits.read(parent_bits)
                last_parent = offset
            elif comp in (COMPRESSION_SELF_0, COMPRESSION_SELF_1):
                if comp == COMPRESSION_SELF_1:
                    last_self += 1
                comp = COMPRESSION_SELF
                offset = last_self
            elif comp == COMPRESSION_PARENT_SELF:
                comp = COMPRESSION_PARENT
                offset = (hunknum * hunk_bytes) // unit_bytes
                last_parent = offset
            elif comp in (COMPRESSION_PARENT_0, COMPRESSION_PARENT_1):
                if comp == COMPRESSION_PARENT_1:
                    last_parent += hunk_bytes // unit_bytes
                comp = COMPRESSION_PARENT
                offset = last_parent
            else:
                raise CHDError(f"Invalid map compression type: {comp}")

            base = hunknum * 12
            raw_map[base] = comp
            raw_map[base + 1:base + 4] = length.to_bytes(3, 'big')
            raw_map[base + 4:base + 10] = offset.to_bytes(6, 'big')
            raw_map[base + 10:base + 12] = (crc or 0).to_bytes(2, 'big')

            entry = CHDMapEntry()
            entry.compression = comp
            entry.comp_length = length
            entry.offset = offset
            entry.crc = crc
            self._map.append(entry)

        if _crc16(bytes(raw_map)) != map_crc:
            raise CHDError(
                f"CHD map checksum mismatch — map decode failed. "
                f"Convert to raw format using: "
                f"chdman extractraw -i {self.path} -o output.img"
            )

        # Reject only codecs the map actually uses
        used_codecs = set()
        for entry in self._map:
            if entry.compression <= COMPRESSION_TYPE_3:
                used_codecs.add(self._header.compressors[entry.compression])
            elif entry.compression == COMPRESSION_PARENT:
                raise CHDError(
                    f"CHD references a parent file. Convert to standalone "
                    f"format using: chdman extractraw -i {self.path} -o output.img"
                )
        unsupported = used_codecs - SUPPORTED_CODECS
        if unsupported:
            names = ', '.join(
                c.to_bytes(4, 'big').decode('ascii', errors='replace')
                for c in sorted(unsupported)
            )
            raise CHDError(
                f"CHD uses unsupported codec(s): {names}. "
                f"Convert to raw format using: "
                f"chdman extractraw -i {self.path} -o output.img"
            )

    def _read_hunk(self, hunk_num: int) -> bytes:
        """Read and decompress a single hunk."""
        if hunk_num in self._hunk_cache:
            return self._hunk_cache[hunk_num]

        if hunk_num >= len(self._map):
            # Beyond end - return zeros
            return b'\x00' * self._header.hunk_bytes

        entry = self._map[hunk_num]
        hunk_data: bytes

        if entry.compression == COMPRESSION_NONE:
            if entry.offset == 0 and entry.comp_length == 0:
                # Unallocated hunk (uncompressed map only)
                hunk_data = b'\x00' * self._header.hunk_bytes
            else:
                self._file.seek(entry.offset)
                hunk_data = self._file.read(self._header.hunk_bytes)
                if len(hunk_data) < self._header.hunk_bytes:
                    hunk_data += b'\x00' * (self._header.hunk_bytes - len(hunk_data))

        elif entry.compression == COMPRESSION_SELF:
            # Reference to earlier hunk (offset is a hunk number)
            hunk_data = self._read_hunk(entry.offset)

        elif entry.compression <= COMPRESSION_TYPE_3:
            # Compressed with codec from slot
            codec = self._header.compressors[entry.compression]
            self._file.seek(entry.offset)
            comp_data = self._file.read(entry.comp_length)
            hunk_data = self._decompress(comp_data, codec)

        else:
            raise CHDError(f"Unknown compression type: {entry.compression}")

        if len(hunk_data) != self._header.hunk_bytes:
            raise CHDError(
                f"Hunk {hunk_num} decompressed to {len(hunk_data)} bytes, "
                f"expected {self._header.hunk_bytes}"
            )
        if entry.crc is not None and _crc16(hunk_data) != entry.crc:
            raise CHDError(f"Hunk {hunk_num} failed CRC check — corrupt CHD data")

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
        elif codec == CHD_CODEC_HUFFMAN:
            return self._decompress_huffman(data)
        elif codec == CHD_CODEC_FLAC:
            return self._decompress_flac(data)
        else:
            codec_str = codec.to_bytes(4, 'big').decode('ascii', errors='replace')
            raise CHDError(f"Unsupported codec: {codec_str}")

    def _decompress_zlib(self, data: bytes) -> bytes:
        """Decompress raw-deflate data (MAME zlib codec has no header)."""
        try:
            return zlib.decompress(data, -15)
        except zlib.error:
            try:
                return zlib.decompress(data)
            except zlib.error as e:
                raise CHDError(f"Corrupt zlib hunk data: {e}")

    def _decompress_lzma(self, data: bytes) -> bytes:
        """
        Decompress LZMA data. MAME's lzma codec stores a raw LZMA1 stream
        with no properties header; the properties are the encoder defaults
        (lc=3, lp=0, pb=2) with the dictionary sized from the hunk size.
        """
        if not HAS_LZMA:
            raise CHDError("LZMA compression requires the lzma module")

        # Mirror LzmaEncProps_Normalize for level 9 / reduceSize = hunk size:
        # the dictionary shrinks to the smallest power of two (or 3 << k)
        # >= the hunk size, bounded below at 4KB
        hunk_bytes = self._header.hunk_bytes
        dict_size = 1 << 26  # level 9 default (64MB)
        if hunk_bytes < dict_size:
            for bits in range(11, 31):
                if hunk_bytes <= (2 << bits):
                    dict_size = 2 << bits
                    break
                if hunk_bytes <= (3 << bits):
                    dict_size = 3 << bits
                    break

        filters = [{
            'id': lzma.FILTER_LZMA1,
            'lc': 3, 'lp': 0, 'pb': 2,
            'dict_size': dict_size,
        }]
        try:
            decompressor = lzma.LZMADecompressor(
                format=lzma.FORMAT_RAW, filters=filters)
            return decompressor.decompress(data, self._header.hunk_bytes)
        except lzma.LZMAError as e:
            raise CHDError(f"Corrupt LZMA hunk data: {e}")

    def _decompress_huffman(self, data: bytes) -> bytes:
        """Decompress MAME 'huff' codec data (8-bit Huffman coded bytes)."""
        bits = _BitReader(data)
        decoder = _HuffmanDecoder(256, 16)
        decoder.import_tree_huffman(bits)
        return bytes(
            decoder.decode_one(bits) for _ in range(self._header.hunk_bytes)
        )

    def _decompress_flac(self, data: bytes) -> bytes:
        """
        Decompress MAME 'flac' codec data: an endianness marker byte
        ('L' or 'B') followed by raw FLAC frames of 16-bit stereo samples.
        """
        if not data or data[0] not in (ord('L'), ord('B')):
            raise CHDError("Invalid FLAC hunk endianness marker")
        byteorder = 'little' if data[0] == ord('L') else 'big'

        total_samples = self._header.hunk_bytes // 2
        decoder = _FlacFrameDecoder(data[1:])
        out = bytearray()
        decoded = 0
        while decoded < total_samples:
            samples = decoder.decode_frame()
            decoded += len(samples)
            for s in samples:
                out += (s & 0xFFFF).to_bytes(2, byteorder)
        return bytes(out[:self._header.hunk_bytes])

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
