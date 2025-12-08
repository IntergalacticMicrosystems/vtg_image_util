# NOTE: Much of this is untested ~ USE AT YOUR OWN RISK!
# Completely untested on Linux or MacOS at this point

# Vtg Disk Image Utility

A cross-platform utility for reading and writing Victor 9000 and IBM PC floppy and hard disk images.

## Features

- **Victor 9000 Support**
  - FAT12 floppy disks (single and double-sided)
  - Hard disk images with multiple partitions
  - CP/M-86 floppy disks (read-only)

- **IBM PC Support**
  - FAT12 floppy disks (360KB, 720KB, 1.2MB, 1.44MB)

- **Operations**
  - List directory contents (with recursive option)
  - Copy files to/from disk images (with wildcard support)
  - Delete files from disk images
  - Create new blank disk images
  - View and modify file attributes
  - Verify disk image integrity
  - View disk information and statistics

- **Interfaces**
  - Command-line interface (CLI)
  - Graphical user interface (GUI) with drag-and-drop support

## Requirements

- Python 3.12 or later
- wxPython 4.2+ (for GUI only)

## Installation

### From Source

```bash
# Clone or download the repository
cd vtg_image_util

# Install dependencies (GUI only)
pip install wxPython

# Run directly
python -m vtg_image_util --help
python -m vtg_image_util.gui
```

### Install as Package

```bash
pip install -e .
```

## Usage

### Command Line Interface

#### List Files

```bash
# List root directory
vtg_image_util list disk.img

# List subdirectory
vtg_image_util list disk.img:\SUBDIR

# List recursively (all subdirectories)
vtg_image_util list disk.img -r

# Hard disk - list partitions
vtg_image_util list vichd.img

# Hard disk - list partition contents
vtg_image_util list vichd.img:0:\

# Hard disk - list all partitions recursively
vtg_image_util list vichd.img -r

# JSON output
vtg_image_util list disk.img --json
```

#### Copy Files

```bash
# Copy single file from image
vtg_image_util copy disk.img:\COMMAND.COM ./

# Copy with wildcards
vtg_image_util copy disk.img:\*.COM ./output/

# Copy all files
vtg_image_util copy disk.img:\*.* ./output/

# Copy recursively (include subdirectories)
vtg_image_util copy disk.img:\* ./output/ -r

# Copy to image
vtg_image_util copy localfile.txt disk.img:\FILE.TXT

# Hard disk partitions
vtg_image_util copy vichd.img:0:\FILE.COM ./
vtg_image_util copy localfile.txt vichd.img:1:\FILE.TXT
```

#### Delete Files

```bash
vtg_image_util delete disk.img:\FILE.COM
vtg_image_util delete vichd.img:0:\FILE.COM
```

#### Create Disk Images

```bash
# Victor 9000 floppy (single-sided ~600KB)
vtg_image_util create new.img -t victor-ss

# Victor 9000 floppy (double-sided ~1.2MB)
vtg_image_util create new.img -t victor-ds

# IBM PC floppies
vtg_image_util create new.img -t 360K
vtg_image_util create new.img -t 720K
vtg_image_util create new.img -t 1.2M
vtg_image_util create new.img -t 1.44M

# With volume label
vtg_image_util create new.img -t victor-ds -l MYDISK

# Overwrite existing
vtg_image_util create new.img -t 1.44M -f
```

#### View/Modify Attributes

```bash
# View attributes
vtg_image_util attr disk.img:\FILE.COM

# Set read-only
vtg_image_util attr disk.img:\FILE.COM -- +R

# Clear archive, set hidden
vtg_image_util attr disk.img:\FILE.COM -- -A +H
```

Attribute flags: `R` (read-only), `H` (hidden), `S` (system), `A` (archive)

#### Disk Information

```bash
vtg_image_util info disk.img
vtg_image_util info vichd.img:0    # Specific partition
vtg_image_util info disk.img -v    # Verbose/technical details
```

#### Verify Disk Integrity

```bash
vtg_image_util verify disk.img
vtg_image_util verify vichd.img:0  # Specific partition
```

#### Global Options

```bash
--version        Show version
-v, --verbose    Detailed output
-q, --quiet      Suppress non-essential output
--json           JSON output format
--help-syntax    Detailed help with examples
```

### Graphical User Interface

```bash
# Launch GUI
python -m vtg_image_util.gui

# Open specific image
python -m vtg_image_util.gui disk.img
```

**GUI Features:**
- Open/Save/Close disk images
- Browse directories with file list
- Copy files via drag-and-drop or menu
- Delete files with confirmation
- View file properties
- Search/filter files (supports wildcards)
- Recent files menu
- Partition selection for hard disks

## Path Syntax

### Floppy Disks
```
image.img                  Image file (list root)
image.img:\                Root directory
image.img:\FILE.COM        File in root
image.img:\SUBDIR          Subdirectory
image.img:\SUBDIR\FILE     File in subdirectory
```

### Hard Disks (with partitions)
```
image.img                  Image file (list partitions)
image.img:0:\              Partition 0 root
image.img:0:\FILE.COM      File in partition 0
image.img:1:\SUBDIR        Subdirectory in partition 1
```

### Wildcards
```
*        Matches any characters (including none)
?        Matches exactly one character
*.COM    All .COM files
*.*      All files with extensions
*        All files (with or without extension)
```

## Building Standalone Executables

### Windows

Requires PyInstaller:

```bash
pip install pyinstaller

cd vtg_image_util
pyinstaller vtg_image_util.spec --clean
```

Output in `dist/`:
- `vtg_image_util.exe` - CLI version (console)
- `vtg_image_util_gui.exe` - GUI version (windowed)

### macOS

```bash
pip install pyinstaller

cd vtg_image_util
pyinstaller vtg_image_util.spec --clean
```

Note: You may need to create a macOS-specific .spec file or modify the existing one for proper app bundle creation.

### Linux

```bash
pip install pyinstaller

cd vtg_image_util
pyinstaller vtg_image_util.spec --clean
```

For distribution, consider creating an AppImage or packaging for your distribution.

## Platform Notes

### Windows
- Executables are self-contained single files
- No Python installation required for .exe files
- Path separator in image paths uses backslash: `disk.img:\FILE`

### macOS
- Install wxPython: `pip install wxPython`
- For Apple Silicon, ensure you have the ARM64 version of Python
- Run from terminal: `python -m vtg_image_util.gui`

### Linux
- Install wxPython: `pip install wxPython`
- On some distributions, you may need GTK development libraries:
  ```bash
  # Debian/Ubuntu
  sudo apt install libgtk-3-dev

  # Fedora
  sudo dnf install gtk3-devel
  ```
- Run from terminal: `python -m vtg_image_util.gui`

## Technical Details

### Victor 9000 Floppy Format
- FAT12 filesystem
- 4 sectors per cluster (2048 bytes)
- Single-sided: ~600KB, Double-sided: ~1.2MB
- Variable track geometry (GCR encoding on real hardware)

### Victor 9000 Hard Disk Format
- Physical disk label at sector 0
- Multiple partitions (virtual volumes)
- Variable cluster size (typically 32KB)
- Each partition has independent FAT and directory

### IBM PC Floppy Format
- Standard FAT12 with BIOS Parameter Block
- Boot signature 0x55AA identifies format
- Geometry read from BPB fields

### Image Type Detection
- File size > 2MB with valid label: Victor hard disk
- Boot signature 0x55AA + valid BPB: IBM PC floppy
- Default: Victor 9000 floppy

## File Structure

```
vtg_image_util/
├── vtg_image_util/          # Main package
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── commands.py          # CLI command handlers
│   ├── floppy.py            # Floppy disk classes
│   ├── harddisk.py          # Hard disk classes
│   ├── cpm.py               # CP/M support
│   ├── fat12.py             # FAT12 implementation
│   ├── creator.py           # Disk creation
│   ├── verify.py            # Disk verification
│   ├── info.py              # Disk information
│   └── gui/                 # GUI package
│       ├── __init__.py
│       ├── __main__.py      # GUI entry point
│       ├── main.py          # App initialization
│       ├── main_frame.py    # Main window
│       ├── file_list.py     # File list control
│       ├── toolbar.py       # Toolbar
│       ├── dialogs.py       # Dialog windows
│       └── ...
├── example_disks/           # Test disk images
├── vtg_image_util.spec      # PyInstaller spec
├── cli_main.py              # CLI executable entry
├── gui_main.py              # GUI executable entry
└── README.md
```

## License

This project is provided as-is for working with vintage Victor 9000 disk images.

## Acknowledgments

- Victor 9000 technical documentation
- FAT12 filesystem specifications
- wxPython project
