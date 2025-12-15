# MAME CHD (Compressed Hunks of Data) File Format — Standalone Reference

This is a **practical, implementation-oriented** overview of the CHD container format as used by MAME.
It is intended for LLM/tooling use (e.g., writing parsers, validators, or explaining CHDs) **without requiring access to MAME’s source tree**.

## What CHD is

CHD (“Compressed Hunks of Data”) is a **random-access container** for large block-addressable media images (hard disks, CD/GD/DVD, laserdisc A/V captures, etc.). Data is stored in fixed-size **hunks** and optionally compressed. CHDs can be **delta** files that reference a **parent CHD** for unchanged data.

All multi-byte integers stored in CHD headers/maps/metadata are **big-endian** (“Motorola order”).

## Core terminology

- **logical bytes**: total size of the represented raw medium in bytes.
- **hunk**: the primary independently addressable block; `hunkbytes` bytes per hunk.
- **unit**: smaller addressing granularity used primarily for parent references; `unitbytes` bytes per unit.
- **map**: per-hunk table describing where/how each hunk’s data is stored (or referenced).
- **metadata**: linked-list of tagged blobs describing the contained medium (geometry, CD tracks, A/V properties, etc.).

## File signature and versions

Every CHD starts with an 8-byte ASCII tag:

```text
tag = "MComprHD"
```

CHD has multiple on-disk versions (1–5). Modern MAME uses **v5** as the current format, but older versions exist in the wild.

This document focuses on **v5** because it is the current format.

## V5 header layout (124 bytes)

Offsets are from file start. All integers big-endian.

```c
// V5 header (size = 124 bytes)
struct chd_header_v5 {
  char     tag[8];            // "MComprHD"
  u32be    length;            // must be 124 for v5
  u32be    version;           // 5
  u32be    compressors[4];    // codec IDs (FourCC-like tags), see below
  u64be    logicalbytes;
  u64be    mapoffset;         // offset to map (uncompressed map may sit here)
  u64be    metaoffset;        // offset to first metadata item (0 if none)
  u32be    hunkbytes;         // hunk size in bytes
  u32be    unitbytes;         // unit size in bytes
  u8       rawsha1[20];       // SHA-1 of raw data
  u8       sha1[20];          // SHA-1 of raw+metadata (combined)
  u8       parentsha1[20];    // parent's combined SHA-1 (all zeros => no parent)
};
```

Important v5 rules:

- **Parent presence**: if `parentsha1` is non-zero, the CHD is a delta file and requires a parent CHD to fully reconstruct data.
- **“Compressed vs uncompressed”**: v5 treats the CHD as “compressed” if `compressors[0] != 0` (i.e., codec #0 is not `CHD_CODEC_NONE`).

## Codec identifiers (v5)

In v5, the `compressors[0..3]` fields store **codec identifiers**. These are 32-bit tags (often FourCC-like) that identify the decompression method.

Common ones:

- `CHD_CODEC_NONE` (`0`)
- `CHD_CODEC_ZLIB` (`'zlib'`)
- `CHD_CODEC_ZSTD` (`'zstd'`)
- `CHD_CODEC_LZMA` (`'lzma'`)
- `CHD_CODEC_HUFFMAN` (`'huff'`)
- `CHD_CODEC_FLAC` (`'flac'`)
- CD frontends like `CHD_CODEC_CD_ZLIB` (`'cdzl'`), `CHD_CODEC_CD_FLAC` (`'cdfl'`), etc.
- A/V: `CHD_CODEC_AVHUFF` (`'avhu'`)

Notes:

- A v5 CHD may list up to **four** codecs; each hunk can choose among them (or be stored uncompressed, or be a self/parent reference).
- Some codecs may be **lossy** (notably certain A/V representations). In those cases, integrity checks may be computed over the compressed payload rather than the decompressed output (tooling should treat the CRC semantics as codec-dependent).

## V5 map: two cases

The **map** provides the per-hunk storage description. In v5, the on-disk map encoding depends on whether the CHD is “compressed” (`compressors[0] != 0`).

### Case A: v5 “uncompressed CHD” (no codecs)

In this mode:

- `compressors[0] == 0` (and typically all four are zero)
- `mapentrybytes = 4`
- Each map entry is a single `u32be`, interpreted as a **file offset measured in hunks**.

```c
// Uncompressed v5 map entry (4 bytes)
u32be block_index; // file_offset_bytes = block_index * hunkbytes
```

Semantics:

- If `block_index != 0`: read/write raw hunk at `block_index * hunkbytes` in the CHD file.
- If `block_index == 0`:
  - If there is a parent CHD: read that hunk from the parent.
  - Else: treat as all-zero data.

This mode supports writable CHDs (compressed CHDs are typically treated as read-only by many implementations).

### Case B: v5 “compressed CHD” (codecs present)

In this mode:

- `compressors[0] != 0`
- `mapentrybytes = 12`
- The *expanded* per-hunk map entry is:

```c
// Expanded v5 map entry (12 bytes)
struct v5_map_entry {
  u8     comp;        // compression selector / pseudo-type (see below)
  u24be  complen;     // compressed length in bytes (0 for references)
  u48be  offset;      // file offset (bytes) OR reference value (see below)
  u16be  crc16;       // CRC-16 (meaning depends on codec lossiness)
};
```

`comp` meanings:

- `0..3` = “codec slot”: use `compressors[comp]` to decompress `complen` bytes from `offset` (a byte offset within the CHD file).
- `4` = stored uncompressed: read `hunkbytes` raw bytes from `offset`.
- `5` = **self reference**: this hunk is identical to another hunk in the same CHD; `offset` holds the referenced hunk number.
- `6` = **parent reference**: this hunk is sourced from the parent; `offset` holds a parent **unit index** (not a byte offset). Readers reconstruct the hunk by reading `hunkbytes` bytes from `offset * parent.unitbytes` in the parent image.

#### Compressed-map encoding (the map itself can be compressed)

For “compressed CHDs”, the **on-disk map** is typically stored in a compact bit-packed form at `mapoffset`, and expands to `hunkcount * 12` bytes of per-hunk entries.

The v5 “compressed map” begins with a 16-byte header:

```c
struct v5_compressed_map_header {
  u32be  length;         // total compressed map byte length (excluding this header)
  u48be  datastart;      // offset of first data block (used during decoding)
  u16be  crc16;          // CRC-16 of the expanded map (hunkcount * 12 bytes)
  u8     lengthbits;     // bit-width used to encode complen fields
  u8     hunkbits;       // bit-width used to encode self refs
  u8     parentunitbits; // bit-width used to encode parent unit refs
  u8     reserved;
};
```

The per-hunk entries are then encoded using a combination of:

- Huffman-coded compression types
- Bit-packed lengths/offsets/references using the bit-widths in the header
- Small run-length optimizations for repeated values

Implementing the compressed-map decoder is non-trivial: it is a specialized combination of Huffman coding, bit packing, and small RLE/self/parent reference optimizations. If you need your own decoder, plan to implement the full bitstream format described by the header fields above.

## Metadata: tagged linked list

CHD metadata is a linked list starting at `metaoffset` (from the CHD header). Each metadata item has a 16-byte header followed by `length` bytes of data.

```c
// Metadata item header (16 bytes)
struct chd_metadata_header {
  u32be  metatag;   // 4-byte tag (e.g., 'GDDD', 'CHTR', 'AVAV', ...)
  u8     flags;     // includes CHD_MDFLAGS_CHECKSUM (0x01)
  u24be  length;    // data length in bytes
  u64be  next;      // offset of next metadata header (0 => end)
  // followed by `length` bytes of metadata payload
};
```

Common tags used by MAME include (non-exhaustive):

- Hard disk: `HARD_DISK_METADATA_TAG` (`'GDDD'`) with format string `HARD_DISK_METADATA_FORMAT`
- CD tracks: `CDROM_TRACK_METADATA_TAG` (`'CHTR'`), `CDROM_TRACK_METADATA2_TAG` (`'CHT2'`)
- GD-ROM tracks: `GDROM_TRACK_METADATA_TAG` (`'CHGD'`)
- DVD: `DVD_METADATA_TAG` (`'DVD '`)
- A/V: `AV_METADATA_TAG` (`'AVAV'`)

## Parent/delta behavior (v5)

Delta CHDs avoid storing identical data:

- Map entries may reference **self** (another earlier hunk in the same file).
- Map entries may reference **parent** (data is read from the parent CHD).

Parent matching is primarily done via the parent’s **combined SHA-1** (`parentsha1`) plus emulator/front-end search rules (outside the raw file format).

## Practical parsing checklist (v5)

1. Read 8-byte tag; require `"MComprHD"`.
2. Read `length` and `version`; for v5 require `length == 124` and `version == 5`.
3. Read `compressors[4]`, `logicalbytes`, `mapoffset`, `metaoffset`, `hunkbytes`, `unitbytes`, hashes.
4. Decide mode:
   - If `compressors[0] == 0`: uncompressed map; read `hunkcount * 4` bytes at `mapoffset` into `u32be` entries.
   - Else: compressed mode; read the compressed-map header at `mapoffset`, then decompress the map into `hunkcount * 12` expanded entries.
5. To read hunk `N`:
   - Use the map entry to decide: codec slot, raw copy, self ref, parent ref, or unallocated (uncompressed mode with `block_index == 0`).
6. To read metadata:
   - Walk from `metaoffset` using `next` pointers, or search by `(metatag, occurrence-index)` while walking.

## Common pitfalls

- **Endianness**: all header/map/metadata integers are big-endian.
- **Parent references use units**: v5 parent map entries store a parent *unit index*, not a byte offset.
- **Self references are restricted**: writers typically only reference earlier hunks (forward references are not expected).
- **CRC meaning can vary**: for lossy codecs, the CRC may be computed over compressed payload bytes rather than the decompressed hunk.
