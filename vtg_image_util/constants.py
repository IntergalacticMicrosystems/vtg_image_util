"""
Constants for Victor 9000 and IBM PC disk image utilities.
"""

# Sector and cluster sizes
SECTOR_SIZE = 512
DIR_ENTRY_SIZE = 32
SECTORS_PER_CLUSTER = 4  # Victor 9000 uses 4 sectors per cluster
CLUSTER_SIZE = SECTOR_SIZE * SECTORS_PER_CLUSTER  # 2048 bytes per cluster

# FAT entry values
FAT_FREE = 0x000
FAT_BAD = 0xFF7
FAT_EOF_MIN = 0xFF8
FAT_EOF_MAX = 0xFFF

# File attributes
ATTR_READONLY = 0x01
ATTR_HIDDEN = 0x02
ATTR_SYSTEM = 0x04
ATTR_VOLUME = 0x08
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE = 0x20

# Valid 8.3 filename characters
VALID_FILENAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~ ")

# Hard disk specific constants
HD_SECTORS_PER_CLUSTER = 16
HD_CLUSTER_SIZE = SECTOR_SIZE * HD_SECTORS_PER_CLUSTER  # 8192 bytes
HD_FAT_SECTORS = 8
HD_DIR_SECTORS = 20
HD_MAX_DIR_ENTRIES = 312

# Media descriptor bytes
MEDIA_FLOPPY = 0x01
MEDIA_HARDDISK = 0x02

# Hard disk label offsets (Physical Disk Label)
PDL_LABEL_TYPE = 0
PDL_DEVICE_ID = 2
PDL_SERIAL_NUMBER = 4
PDL_SECTOR_SIZE = 20
PDL_IPL_DISK_ADDR = 22
PDL_IPL_LOAD_ADDR = 26
PDL_IPL_LOAD_LEN = 28
PDL_IPL_CODE_ENTRY = 30
PDL_PRIMARY_BOOT_VOL = 34
PDL_CONTROLLER_PARAMS = 36

# Virtual volume label offsets
VVL_LABEL_TYPE = 0
VVL_VOLUME_NAME = 2
VVL_IPL_DISK_ADDR = 18
VVL_VOLUME_CAPACITY = 30
VVL_DATA_START = 34
VVL_HOST_BLOCK_SIZE = 38
VVL_ALLOCATION_UNIT = 40
VVL_NUM_DIR_ENTRIES = 42
VVL_RESERVED = 44          # 16 bytes reserved
VVL_ASSIGNMENT_COUNT = 60  # Configuration information starts here

# CP/M filesystem constants
CPM_DIR_ENTRY_SIZE = 32
CPM_DELETED = 0xE5
CPM_RECORD_SIZE = 128        # CP/M record size (128 bytes)
CPM_RECORDS_PER_EXTENT = 128  # Max records per directory extent
CPM_EXTENT_SIZE = CPM_RECORD_SIZE * CPM_RECORDS_PER_EXTENT  # 16KB per extent

# Victor 9000 CP/M-86 disk geometry
CPM_SECTOR_SIZE = 512
CPM_BLOCK_SIZE = 2048        # 4 sectors per allocation block
CPM_SECTORS_PER_BLOCK = 4
CPM_DIR_START_SECTOR = 76    # Directory starts at sector 76
CPM_DIR_SECTORS = 18         # 18 directory sectors (every 2nd sector: 76, 78, ..., 110)
CPM_DIR_INTERLEAVE = 2       # Directory sector interleave factor
CPM_DATA_START_SECTOR = 112  # Data area (block 0) starts at sector 112
CPM_MAX_BLOCKS = 556         # 16-bit block pointers (disk size / block size)
CPM_BLOCKS_PER_EXTENT = 8    # 8 x 16-bit block pointers per directory entry
