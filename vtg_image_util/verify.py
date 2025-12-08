"""
Disk verification and repair for Victor 9000 and IBM PC disk images.

Provides functions to check disk integrity and optionally repair issues.
"""

from dataclasses import dataclass, field
from typing import Any

from .constants import FAT_FREE, FAT_EOF_MIN, FAT_BAD
from .fat12 import FAT12Base
from .floppy import V9KDiskImage, IBMPCDiskImage
from .harddisk import V9KHardDiskImage, V9KPartition
from .cpm import V9KCPMDiskImage


@dataclass
class VerificationResult:
    """Results from disk verification."""
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    # Statistics
    files_checked: int = 0
    directories_checked: int = 0
    clusters_in_use: int = 0
    lost_clusters: int = 0
    cross_linked_clusters: list[int] = field(default_factory=list)
    bad_clusters: int = 0

    def add_error(self, message: str):
        """Add an error (disk is invalid)."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        """Add a warning (disk usable but has issues)."""
        self.warnings.append(message)

    def add_info(self, message: str):
        """Add informational message."""
        self.info.append(message)


def verify_disk(disk: Any, verbose: bool = False) -> VerificationResult:
    """
    Verify a disk image for consistency.

    Args:
        disk: A disk image object
        verbose: Whether to include detailed information

    Returns:
        VerificationResult with findings
    """
    if isinstance(disk, V9KHardDiskImage):
        return _verify_harddisk(disk, verbose)
    elif isinstance(disk, V9KCPMDiskImage):
        return _verify_cpm_disk(disk, verbose)
    elif isinstance(disk, (V9KDiskImage, IBMPCDiskImage, V9KPartition)):
        return _verify_fat12_disk(disk, verbose)
    else:
        result = VerificationResult()
        result.add_error(f"Unknown disk type: {type(disk).__name__}")
        return result


def _verify_fat12_disk(disk: FAT12Base, verbose: bool = False) -> VerificationResult:
    """Verify a FAT12 disk or partition."""
    result = VerificationResult()

    # Track which clusters are used by files
    cluster_usage: dict[int, list[str]] = {}  # cluster -> list of files using it

    # Verify FAT structure
    result.add_info("Checking FAT structure...")
    _verify_fat_structure(disk, result)

    # Verify directory structure and build cluster usage map
    result.add_info("Checking directory structure...")
    _verify_directory(disk, None, "", cluster_usage, result)

    # Check for cross-linked clusters (used by multiple files)
    for cluster, files in cluster_usage.items():
        if len(files) > 1:
            result.add_error(f"Cross-linked cluster {cluster}: used by {', '.join(files)}")
            result.cross_linked_clusters.append(cluster)

    # Check for lost clusters (allocated but not used by any file)
    result.add_info("Checking for lost clusters...")
    _find_lost_clusters(disk, cluster_usage, result)

    # Count bad clusters
    for cluster in range(2, disk.total_clusters + 2):
        if disk.get_fat_entry(cluster) == FAT_BAD:
            result.bad_clusters += 1

    if result.bad_clusters > 0:
        result.add_warning(f"Found {result.bad_clusters} bad cluster(s) marked in FAT")

    # Summary
    result.clusters_in_use = len(cluster_usage)

    if verbose:
        result.add_info(f"Files checked: {result.files_checked}")
        result.add_info(f"Directories checked: {result.directories_checked}")
        result.add_info(f"Clusters in use: {result.clusters_in_use}")
        if result.lost_clusters > 0:
            result.add_info(f"Lost clusters: {result.lost_clusters}")

    return result


def _verify_fat_structure(disk: FAT12Base, result: VerificationResult):
    """Verify basic FAT structure."""
    # Check reserved entries (0 and 1)
    entry0 = disk.get_fat_entry(0)
    entry1 = disk.get_fat_entry(1)

    # Entry 0 should contain media descriptor
    if entry0 < 0xF00:
        result.add_warning(f"FAT entry 0 has unusual value: 0x{entry0:03X}")

    # Entry 1 should be end-of-chain marker
    if entry1 < FAT_EOF_MIN:
        result.add_warning(f"FAT entry 1 has unusual value: 0x{entry1:03X}")


def _verify_directory(
    disk: FAT12Base,
    cluster: int | None,
    path: str,
    cluster_usage: dict[int, list[str]],
    result: VerificationResult
):
    """Recursively verify directory structure."""
    try:
        entries = disk.read_directory(cluster)
    except Exception as e:
        result.add_error(f"Cannot read directory {path or 'root'}: {e}")
        return

    result.directories_checked += 1

    for entry in entries:
        if entry.is_free or entry.is_volume_label:
            continue

        if entry.is_dot_entry:
            continue

        entry_path = f"{path}\\{entry.full_name}" if path else entry.full_name

        if entry.is_directory:
            # Verify subdirectory
            if entry.first_cluster < 2:
                result.add_error(f"Directory {entry_path} has invalid first cluster: {entry.first_cluster}")
                continue

            # Check for circular references
            if entry.first_cluster in cluster_usage:
                result.add_error(f"Circular reference: directory {entry_path} points to already-used cluster {entry.first_cluster}")
                continue

            # Mark directory clusters as used
            try:
                chain = disk.follow_chain(entry.first_cluster)
                for c in chain:
                    if c in cluster_usage:
                        cluster_usage[c].append(entry_path)
                    else:
                        cluster_usage[c] = [entry_path]
            except Exception as e:
                result.add_error(f"Invalid cluster chain for directory {entry_path}: {e}")
                continue

            # Recurse into subdirectory
            _verify_directory(disk, entry.first_cluster, entry_path, cluster_usage, result)
        else:
            # Verify file
            result.files_checked += 1

            if entry.file_size == 0:
                if entry.first_cluster != 0:
                    result.add_warning(f"Empty file {entry_path} has non-zero first cluster: {entry.first_cluster}")
                continue

            if entry.first_cluster < 2:
                result.add_error(f"File {entry_path} has invalid first cluster: {entry.first_cluster}")
                continue

            # Verify cluster chain
            try:
                chain = disk.follow_chain(entry.first_cluster)

                # Check chain length vs file size
                expected_clusters = (entry.file_size + disk.cluster_size - 1) // disk.cluster_size
                if len(chain) != expected_clusters:
                    result.add_warning(
                        f"File {entry_path}: size {entry.file_size} bytes suggests {expected_clusters} clusters, "
                        f"but chain has {len(chain)} clusters"
                    )

                # Mark clusters as used
                for c in chain:
                    if c in cluster_usage:
                        cluster_usage[c].append(entry_path)
                    else:
                        cluster_usage[c] = [entry_path]

            except Exception as e:
                result.add_error(f"Invalid cluster chain for file {entry_path}: {e}")


def _find_lost_clusters(
    disk: FAT12Base,
    cluster_usage: dict[int, list[str]],
    result: VerificationResult
):
    """Find clusters that are allocated but not used by any file."""
    lost_chains = []
    visited = set(cluster_usage.keys())

    for cluster in range(2, disk.total_clusters + 2):
        if cluster in visited:
            continue

        entry = disk.get_fat_entry(cluster)

        # Skip free and bad clusters
        if entry == FAT_FREE or entry == FAT_BAD:
            continue

        # This cluster is allocated but not used by any file
        # Follow the chain to count lost clusters
        try:
            chain = disk.follow_chain(cluster)
            for c in chain:
                if c not in visited:
                    visited.add(c)
                    result.lost_clusters += 1

            if chain:
                lost_chains.append((cluster, len(chain)))
        except Exception:
            result.lost_clusters += 1
            visited.add(cluster)

    if lost_chains:
        result.add_warning(f"Found {len(lost_chains)} lost cluster chain(s) totaling {result.lost_clusters} clusters")
        for start, length in lost_chains[:5]:  # Show first 5
            result.add_warning(f"  Lost chain starting at cluster {start}, length {length}")
        if len(lost_chains) > 5:
            result.add_warning(f"  ... and {len(lost_chains) - 5} more")


def _verify_harddisk(disk: V9KHardDiskImage, verbose: bool = False) -> VerificationResult:
    """Verify a Victor 9000 hard disk with all partitions."""
    result = VerificationResult()

    result.add_info(f"Checking hard disk with {disk.partition_count} partition(s)...")

    for idx in range(disk.partition_count):
        partition = disk.get_partition(idx)
        name = partition.volume_label.volume_name.strip()
        result.add_info(f"Checking partition {idx}: {name}")

        part_result = _verify_fat12_disk(partition, verbose)

        # Merge results
        for error in part_result.errors:
            result.add_error(f"Partition {idx}: {error}")
        for warning in part_result.warnings:
            result.add_warning(f"Partition {idx}: {warning}")
        if verbose:
            for info in part_result.info:
                result.add_info(f"  {info}")

        result.files_checked += part_result.files_checked
        result.directories_checked += part_result.directories_checked
        result.clusters_in_use += part_result.clusters_in_use
        result.lost_clusters += part_result.lost_clusters
        result.bad_clusters += part_result.bad_clusters
        result.cross_linked_clusters.extend(part_result.cross_linked_clusters)

    return result


def _verify_cpm_disk(disk: V9KCPMDiskImage, verbose: bool = False) -> VerificationResult:
    """Verify a CP/M disk."""
    result = VerificationResult()

    result.add_info("Checking CP/M disk structure...")

    try:
        files = disk.list_files()
        result.files_checked = len(files)

        # Check for duplicate filenames
        seen_names: dict[str, int] = {}
        for f in files:
            key = f"{f.user}:{f.full_name}"
            if key in seen_names:
                result.add_warning(f"Duplicate file entry: {key}")
            else:
                seen_names[key] = 1

        if verbose:
            result.add_info(f"Files checked: {result.files_checked}")

    except Exception as e:
        result.add_error(f"Error reading CP/M directory: {e}")

    return result


def format_verification_result(result: VerificationResult) -> str:
    """Format verification result as human-readable string."""
    lines = []

    if result.is_valid:
        lines.append("Disk verification: PASSED")
    else:
        lines.append("Disk verification: FAILED")

    lines.append("")

    # Errors
    if result.errors:
        lines.append(f"Errors ({len(result.errors)}):")
        for error in result.errors:
            lines.append(f"  ERROR: {error}")
        lines.append("")

    # Warnings
    if result.warnings:
        lines.append(f"Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            lines.append(f"  WARNING: {warning}")
        lines.append("")

    # Summary
    lines.append("Summary:")
    lines.append(f"  Files checked: {result.files_checked}")
    lines.append(f"  Directories checked: {result.directories_checked}")
    lines.append(f"  Clusters in use: {result.clusters_in_use}")

    if result.lost_clusters > 0:
        lines.append(f"  Lost clusters: {result.lost_clusters}")
    if result.bad_clusters > 0:
        lines.append(f"  Bad clusters: {result.bad_clusters}")
    if result.cross_linked_clusters:
        lines.append(f"  Cross-linked clusters: {len(result.cross_linked_clusters)}")

    return '\n'.join(lines)
