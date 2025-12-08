## Project Overview
Victor 9000 disk image utility written in Python 3.12+.
Supports FAT12 filesystem operations including subdirectories.
Supports Victor 9000 floppy/hard disk images and IBM PC floppy images.

## Usage

### List files (Floppy)
```bash
vtg_image_util.py list disk.img                    # List root directory
vtg_image_util.py list disk.img:\SUBDIR            # List subdirectory
vtg_image_util.py list disk.img --json             # JSON output
```

### List files (IBM PC Floppy)
```bash
vtg_image_util.py list DOS622.IMG                  # List root directory
vtg_image_util.py list DOS622.IMG:\SUBDIR          # List subdirectory
vtg_image_util.py list DOS622.IMG --json           # JSON output
```

### List files (Victor Hard Disk)
```bash
vtg_image_util.py list vichd.img                   # List partitions
vtg_image_util.py list vichd.img:0:\               # List root of partition 0
vtg_image_util.py list vichd.img:1:\SUBDIR         # List subdirectory on partition 1
vtg_image_util.py list vichd.img --json            # JSON output (partitions)
```

### Copy from image (Floppy)
```bash
vtg_image_util.py copy disk.img:\COMMAND.COM c:\temp\command.com    # Single file
vtg_image_util.py copy disk.img:\*.* c:\temp\                       # Wildcard copy
vtg_image_util.py copy disk.img:\* c:\temp\                         # All files (incl. no extension)
vtg_image_util.py copy disk.img:\*.COM c:\temp\                     # Pattern match
vtg_image_util.py copy disk.img:\* c:\temp\ -r                      # Recursive with subdirs
```

### Copy from image (Hard Disk)
```bash
vtg_image_util.py copy vichd.img:0:\COMMAND.COM c:\temp\            # From partition 0
vtg_image_util.py copy vichd.img:1:\*.* c:\temp\                    # Wildcard from partition 1
vtg_image_util.py copy vichd.img:2:\* c:\temp\ -r                   # Recursive from partition 2
```

### Copy to image
```bash
vtg_image_util.py copy c:\temp\file.txt disk.img:\FILE.TXT          # Floppy
vtg_image_util.py copy c:\temp\file.txt vichd.img:0:\FILE.TXT       # Hard disk partition 0
```

### Delete file
```bash
vtg_image_util.py delete disk.img:\COMMAND.COM                      # Floppy
vtg_image_util.py delete vichd.img:0:\COMMAND.COM                   # Hard disk partition 0
```

### Options
- `--json` - Output in JSON format (available for all commands)
- `-r, --recursive` - Copy subdirectories recursively (copy command)

## Features
- Copy files from image (with wildcard support)
- Copy files to image
- Delete files on image
- List directory contents
- Full subdirectory navigation
- JSON output mode
- 8.3 filename validation (no LFN support)
- Victor 9000 hard disk support with multiple partitions
- IBM PC FAT12 floppy support (auto-detected)

## Technical Notes

### Victor 9000 Floppy Disks
- Victor 9000 uses 4 sectors per cluster (2048 bytes)
- FAT12 filesystem with 12-bit cluster entries
- Disk geometry detected from boot sector flags (bit 0 = double-sided)
- Double-sided: FAT at sectors 1-4, directory at 5-12, data at 13+
- Single-sided: FAT at sectors 1-2, directory at 3-10, data at 11+

### IBM PC Floppy Disks
- Standard FAT12 with BIOS Parameter Block (BPB) in boot sector
- Supports 360KB, 720KB, 1.2MB, 1.44MB formats (auto-detected from BPB)
- Variable sectors per cluster (1-2, read from BPB)
- Boot signature 0x55AA at offset 0x1FE identifies IBM PC format
- All geometry parameters read from BPB fields

### Victor 9000 Hard Disks
- Physical disk label at sector 0 with virtual volume list
- Each partition has its own virtual volume label
- Variable sectors per cluster (typically 64 sectors = 32KB)
- FAT12 with size based on partition capacity

### Image Type Auto-Detection
- File size >2MB: Victor hard disk
- Boot signature 0x55AA + valid BPB: IBM PC floppy
- Victor hard disk label structure: Victor hard disk
- Default: Victor 9000 floppy

## Key Files
- `vtg_image_util.py` - Main utility implementation
- `format_docs/CPM_disk_summary.md` - CPM test disk images details
- `format_docs/victor_boot_sector_layout.md` - Boot sector structure reference
- `format_docs/victor_floppy_sector_layout.md` - Sector layout reference
- `format_docs/victor_9000_floppy_disk_notes.md` - More notes on floppy format
- `format_docs/fat12_floppy_format.md` - FAT12 filesystem reference
- `format_docs/victor_hard_drive_layout.md` - Victor hard disk info
- `format_docs/victor_9000_hard_disk_format.md` - Victor hard disk info
- `format_docs/ibm_pc_floppy_formats.md` - IBM PC floppy disk formats
- `example_disks/DOS622.IMG` - IBM PC floppy disk test file
- `example_disks/vichd.img` - Victor hard disk test file

## Key Directories
- `example_disks/` - Example disk images for testing
- `example_disks/CPM86` - Example Victor 9000 CPM/86 disk images for testing
- `example_disks/DOS622` - Reference files extracted from DOS622.img
- `example_disks/files/` - Reference files extracted from disk.img
- `example_disks/vichd/` - Reference files extracted from vichd.img

