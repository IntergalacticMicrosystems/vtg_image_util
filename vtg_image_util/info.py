"""
Disk information and statistics for Victor 9000 disk images.

Provides functions to analyze disk images and report capacity, usage, etc.
"""

from typing import Any

from .constants import SECTOR_SIZE, FAT_FREE, FAT_EOF_MIN
from .fat12 import FAT12Base
from .floppy import V9KDiskImage, IBMPCDiskImage
from .harddisk import V9KHardDiskImage, V9KPartition
from .cpm import V9KCPMDiskImage
from .utils import detect_image_type


def get_disk_info(disk: Any) -> dict[str, Any]:
    """
    Get comprehensive information about a disk image.

    Args:
        disk: A disk image object (V9KDiskImage, IBMPCDiskImage,
              V9KHardDiskImage, V9KPartition, or V9KCPMDiskImage)

    Returns:
        Dictionary containing disk information
    """
    if isinstance(disk, V9KHardDiskImage):
        return _get_harddisk_info(disk)
    elif isinstance(disk, V9KCPMDiskImage):
        return _get_cpm_disk_info(disk)
    elif isinstance(disk, (V9KDiskImage, IBMPCDiskImage, V9KPartition)):
        return _get_fat12_disk_info(disk)
    else:
        return {'error': f'Unknown disk type: {type(disk).__name__}'}


def _get_fat12_disk_info(disk: FAT12Base) -> dict[str, Any]:
    """Get information for a FAT12 disk or partition."""
    # Calculate cluster usage from FAT
    total_clusters = disk.total_clusters
    free_clusters = 0
    used_clusters = 0
    bad_clusters = 0

    for cluster in range(2, total_clusters + 2):
        entry = disk.get_fat_entry(cluster)
        if entry == FAT_FREE:
            free_clusters += 1
        elif entry == 0xFF7:  # Bad cluster marker
            bad_clusters += 1
        else:
            used_clusters += 1

    cluster_size = disk.cluster_size
    total_bytes = total_clusters * cluster_size
    free_bytes = free_clusters * cluster_size
    used_bytes = used_clusters * cluster_size

    # Count files and directories
    file_count, dir_count = _count_entries(disk, None)

    # Determine disk type
    if isinstance(disk, V9KDiskImage):
        disk_type = 'Victor 9000 Floppy'
    elif isinstance(disk, IBMPCDiskImage):
        disk_type = 'IBM PC Floppy'
    elif isinstance(disk, V9KPartition):
        disk_type = 'Victor 9000 Hard Disk Partition'
    else:
        disk_type = 'FAT12'

    return {
        'type': disk_type,
        'filesystem': 'FAT12',
        'readonly': getattr(disk, 'readonly', False),
        'cluster_size': cluster_size,
        'sectors_per_cluster': disk.sectors_per_cluster,
        'total_clusters': total_clusters,
        'free_clusters': free_clusters,
        'used_clusters': used_clusters,
        'bad_clusters': bad_clusters,
        'total_bytes': total_bytes,
        'free_bytes': free_bytes,
        'used_bytes': used_bytes,
        'total_formatted': _format_size(total_bytes),
        'free_formatted': _format_size(free_bytes),
        'used_formatted': _format_size(used_bytes),
        'percent_used': round(used_clusters / total_clusters * 100, 1) if total_clusters > 0 else 0,
        'file_count': file_count,
        'directory_count': dir_count,
        'fat_sectors': disk.fat_sectors,
        'fat_copies': disk.num_fat_copies,
        'root_dir_sectors': disk.dir_sectors,
        'data_start_sector': disk.data_start,
    }


def _get_harddisk_info(disk: V9KHardDiskImage) -> dict[str, Any]:
    """Get information for a Victor 9000 hard disk."""
    partitions = []
    total_capacity = 0

    for idx in range(disk.partition_count):
        partition = disk.get_partition(idx)
        part_info = _get_fat12_disk_info(partition)
        part_info['index'] = idx
        part_info['name'] = partition.volume_label.volume_name.strip()
        partitions.append(part_info)
        total_capacity += part_info['total_bytes']

    return {
        'type': 'Victor 9000 Hard Disk',
        'filesystem': 'FAT12',
        'readonly': disk.readonly,
        'partition_count': disk.partition_count,
        'total_capacity': total_capacity,
        'total_capacity_formatted': _format_size(total_capacity),
        'partitions': partitions,
    }


def _get_cpm_disk_info(disk: V9KCPMDiskImage) -> dict[str, Any]:
    """Get information for a CP/M disk."""
    files = disk.list_files()
    total_size = sum(f.file_size for f in files)

    return {
        'type': 'Victor 9000 CP/M',
        'filesystem': 'CP/M',
        'readonly': disk.readonly,
        'file_count': len(files),
        'total_file_size': total_size,
        'total_file_size_formatted': _format_size(total_size),
    }


def _count_entries(disk: FAT12Base, cluster: int | None) -> tuple[int, int]:
    """
    Recursively count files and directories.

    Returns:
        Tuple of (file_count, directory_count)
    """
    file_count = 0
    dir_count = 0

    try:
        entries = disk.read_directory(cluster)
        for entry in entries:
            if entry.is_free or entry.is_volume_label or entry.is_dot_entry:
                continue

            if entry.is_directory:
                dir_count += 1
                # Recursively count subdirectory contents
                sub_files, sub_dirs = _count_entries(disk, entry.first_cluster)
                file_count += sub_files
                dir_count += sub_dirs
            else:
                file_count += 1
    except Exception:
        pass  # Ignore errors during counting

    return file_count, dir_count


def _format_size(size_bytes: int) -> str:
    """Format a size in bytes as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def format_disk_info(info: dict[str, Any], verbose: bool = False) -> str:
    """
    Format disk information as a human-readable string.

    Args:
        info: Dictionary from get_disk_info()
        verbose: Whether to include detailed information

    Returns:
        Formatted string
    """
    lines = []

    lines.append(f"Disk Type: {info.get('type', 'Unknown')}")
    lines.append(f"Filesystem: {info.get('filesystem', 'Unknown')}")
    lines.append(f"Mode: {'Read-only' if info.get('readonly') else 'Read-write'}")

    if 'partition_count' in info:
        # Hard disk
        lines.append(f"Partitions: {info['partition_count']}")
        lines.append(f"Total Capacity: {info.get('total_capacity_formatted', 'Unknown')}")
        lines.append("")

        for part in info.get('partitions', []):
            lines.append(f"  Partition {part['index']}: {part.get('name', 'Unnamed')}")
            lines.append(f"    Capacity: {part.get('total_formatted', 'Unknown')}")
            lines.append(f"    Free: {part.get('free_formatted', 'Unknown')} ({100 - part.get('percent_used', 0):.1f}%)")
            lines.append(f"    Files: {part.get('file_count', 0)}, Directories: {part.get('directory_count', 0)}")
    else:
        # Floppy or partition
        lines.append(f"Capacity: {info.get('total_formatted', 'Unknown')}")
        lines.append(f"Used: {info.get('used_formatted', 'Unknown')} ({info.get('percent_used', 0):.1f}%)")
        lines.append(f"Free: {info.get('free_formatted', 'Unknown')}")
        lines.append(f"Files: {info.get('file_count', 0)}")
        lines.append(f"Directories: {info.get('directory_count', 0)}")

        if verbose:
            lines.append("")
            lines.append("Technical Details:")
            lines.append(f"  Cluster size: {info.get('cluster_size', 0)} bytes")
            lines.append(f"  Sectors per cluster: {info.get('sectors_per_cluster', 0)}")
            lines.append(f"  Total clusters: {info.get('total_clusters', 0)}")
            lines.append(f"  Free clusters: {info.get('free_clusters', 0)}")
            lines.append(f"  FAT sectors: {info.get('fat_sectors', 0)} x {info.get('fat_copies', 0)} copies")
            lines.append(f"  Root directory sectors: {info.get('root_dir_sectors', 0)}")
            lines.append(f"  Data start sector: {info.get('data_start_sector', 0)}")

            if info.get('bad_clusters', 0) > 0:
                lines.append(f"  Bad clusters: {info['bad_clusters']}")

    return '\n'.join(lines)
