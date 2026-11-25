
## Victor 9000 Boot Sector Layout

    Track 0 Sector 0

    Byte
    Offset         Name                Description
    0              System disc ID      literally, ff,00h for a system disc
    2              Load address        paragraph to load booted program at. If zero then boot loads in high memory.
    4              Length              paragraph count to load.
    6              Entry offset        I.P. value for transfer of control.
    8              Entry segment       C.S. value for transfer of control.
    10             I.D.                disc identifier.
    18             Part number         system identifier - displayed by early versions of boot.
    26             Sector size         byte count for sectors.
    28             Data start          first data sector on disc (absolute sectors).
    30             Boot start          first absolute sector of program for boot to load at 'load address' for 'length' paragraphs.
    32             Flags               indicators: bit meaning, 15-12 interleave factor (0-15), 0 = 0=single sided, 1=double sided
    34             Disc type           0x10 = MS-DOS (0x01 = CP/M in MAME's source)
    35             Reserved
    38             Speed table         information for speed control proc.
    56             Zone table          high track for each zone.
    71             Sector/track        sectors per track for each zone.
    128            Checksum            16-bit sum of bytes 0-127. Victor DOS reports
                                       "Read fault" for a disk whose label does not match.

### Data disk label written by Victor FORMAT

Bytes 0-127 not listed here are zero (no system disc ID, load address, length or boot start;
data start is 0). The rest of the sector past 129 is zero on the single-sided disk; the
double-sided disk has leftover FORMAT memory at 86-511, which the checksum includes.

    Offset   Single-sided                Double-sided
    26       00 02 (512)                 same
    32       00 00                       01 00 (double-sided)
    34       10                          10
    38-55    04 11 01 3e 49 53 5d 67 71 7b 86 8a 8a 8a 8a 8a 8a 8a  (both)
    56-70    03 0f 1a 25 2f 3b 46 52 61 61 61 61 61 61 61           (both)
    71-79    13 12 11 10 0f 0e 0d 0c 0b                             (both)
    128      7f 0b                       sum of its own bytes 0-127

`vtg_image_util create -t victor-ss|victor-ds` writes this label, with bytes 86-127 zero and
the checksum computed over them. Image sizes are 1224 sectors (single-sided) and 2391 sectors
(double-sided: side 1 has fewer sectors per track).
