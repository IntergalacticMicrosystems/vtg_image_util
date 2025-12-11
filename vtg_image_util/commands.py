"""
Command handlers for Victor 9000 and IBM PC disk image utilities.
"""

import os
from pathlib import Path

from .constants import (
    ATTR_ARCHIVE,
    ATTR_HIDDEN,
    ATTR_READONLY,
    ATTR_SYSTEM,
)
from .cpm import V9KCPMDiskImage
from .exceptions import V9KError
from .floppy import IBMPCDiskImage, V9KDiskImage
from .formatter import OutputFormatter
from .harddisk import V9KHardDiskImage
from .utils import detect_image_type, has_wildcards, parse_image_path, split_internal_path


def cmd_list(args, formatter: OutputFormatter) -> int:
    """Handle the 'list' command."""
    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    recursive = getattr(args, 'recursive', False)

    try:
        image_type = detect_image_type(image_path)

        if image_type == 'harddisk':
            with V9KHardDiskImage(image_path, readonly=True) as disk:
                # If no partition specified
                if partition is None:
                    if recursive:
                        # List all partitions recursively
                        partitions = disk.list_partitions()
                        for i, p in enumerate(partitions):
                            if i > 0 and not formatter.json_mode:
                                print()  # Blank line between partitions
                            part_idx = p['index']
                            part_name = p['name']
                            if not formatter.json_mode:
                                print(f"=== Partition {part_idx}: {part_name} ===")
                                print()
                            volume = disk.get_partition(part_idx)
                            base_path = f"{image_path}:{part_idx}:\\"
                            _list_recursive(volume, None, base_path, formatter)
                    else:
                        # Just list partitions
                        formatter.list_partitions(disk.list_partitions(), image_path)
                    return 0

                volume = disk.get_partition(partition)
                path_components = split_internal_path(internal_path) if internal_path else None

                if recursive:
                    base_path = f"{image_path}:{partition}:\\"
                    if internal_path:
                        base_path += internal_path
                    _list_recursive(volume, path_components, base_path, formatter)
                else:
                    entries = volume.list_files(path_components)
                    if internal_path:
                        display_path = f"{image_path}:{partition}:\\{internal_path}"
                    else:
                        display_path = f"{image_path}:{partition}:\\"
                    formatter.list_files(entries, display_path)

        elif image_type == 'ibmpc':
            # IBM PC FAT12 floppy
            with IBMPCDiskImage(image_path, readonly=True) as disk:
                path_components = split_internal_path(internal_path) if internal_path else None

                if recursive:
                    base_path = f"{image_path}:\\"
                    if internal_path:
                        base_path += internal_path
                    _list_recursive(disk, path_components, base_path, formatter)
                else:
                    entries = disk.list_files(path_components)
                    display_path = f"{image_path}:\\{internal_path}" if internal_path else f"{image_path}:\\"
                    formatter.list_files(entries, display_path)

        elif image_type == 'cpm':
            # Victor 9000 CP/M-86 floppy (no subdirectories)
            with V9KCPMDiskImage(image_path, readonly=True) as disk:
                files = disk.list_files()
                display_path = f"{image_path}:\\"
                formatter.list_cpm_files(files, display_path)

        else:
            # Victor 9000 floppy disk
            with V9KDiskImage(image_path, readonly=True) as disk:
                path_components = split_internal_path(internal_path) if internal_path else None

                if recursive:
                    base_path = f"{image_path}:\\"
                    if internal_path:
                        base_path += internal_path
                    _list_recursive(disk, path_components, base_path, formatter)
                else:
                    entries = disk.list_files(path_components)
                    display_path = f"{image_path}:\\{internal_path}" if internal_path else f"{image_path}:\\"
                    formatter.list_files(entries, display_path)

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except Exception as e:
        formatter.error(f"Unexpected error: {e}")
        return 1


def _list_recursive(disk, path_components: list[str] | None, base_path: str, formatter: OutputFormatter):
    """
    Recursively list directory contents.

    Args:
        disk: The disk object to list from
        path_components: Starting path components (or None for root)
        base_path: Base display path string
        formatter: Output formatter
    """
    # List current directory
    entries = disk.list_files(path_components)
    formatter.list_files(entries, base_path)

    # Find subdirectories and recurse
    for entry in entries:
        if hasattr(entry, 'is_directory') and entry.is_directory:
            if entry.full_name in ('.', '..'):
                continue

            # Build new path for subdirectory
            if path_components:
                new_path = list(path_components) + [entry.full_name]
            else:
                new_path = [entry.full_name]

            # Build display path
            if base_path.endswith('\\'):
                new_display = base_path + entry.full_name
            else:
                new_display = base_path + '\\' + entry.full_name

            # Recurse into subdirectory
            if not formatter.json_mode:
                print()  # Blank line between directories
            _list_recursive(disk, new_path, new_display, formatter)


def cmd_copy(args, formatter: OutputFormatter) -> int:
    """Handle the 'copy' command."""
    source_image, source_partition, source_internal = parse_image_path(args.source)
    dest_image, dest_partition, dest_internal = parse_image_path(args.dest)

    recursive = getattr(args, 'recursive', False)

    # Determine direction
    if source_image is not None and source_internal is not None and dest_image is None:
        # Copy from image to filesystem
        return copy_from_image(source_image, source_partition, source_internal, args.dest, formatter, recursive)

    elif source_image is None and dest_image is not None and dest_internal is not None:
        # Copy from filesystem to image
        return copy_to_image(args.source, dest_image, dest_partition, dest_internal, formatter, recursive)

    else:
        formatter.error("Invalid source/destination. One must be image:path, one must be filesystem path.")
        return 1


def copy_from_image(
    image_path: str,
    partition: int | None,
    internal_path: str,
    dest_path: str,
    formatter: OutputFormatter,
    recursive: bool = False
) -> int:
    """Copy file(s) from disk image to filesystem. Supports wildcards."""
    try:
        path_components = split_internal_path(internal_path)
        if not path_components:
            formatter.error("No file specified in image path")
            return 1

        # Check if wildcards are used
        has_wildcard = has_wildcards(internal_path)

        image_type = detect_image_type(image_path)

        if image_type == 'harddisk':
            if partition is None:
                formatter.error("Partition number required for hard disk image (e.g., image.img:0:\\FILE)")
                return 1
            disk = V9KHardDiskImage(image_path, readonly=True)
            volume = disk.get_partition(partition)
            source_display = f"{image_path}:{partition}:\\{internal_path}"
        elif image_type == 'ibmpc':
            disk = IBMPCDiskImage(image_path, readonly=True)
            volume = disk
            source_display = f"{image_path}:\\{internal_path}"
        elif image_type == 'cpm':
            disk = V9KCPMDiskImage(image_path, readonly=True)
            volume = disk
            source_display = f"{image_path}:\\{internal_path}"
        else:
            disk = V9KDiskImage(image_path, readonly=True)
            volume = disk
            source_display = f"{image_path}:\\{internal_path}"

        try:
            if has_wildcard or recursive:
                # Multi-file copy with wildcards
                matching_files = volume.find_matching_files(path_components, recursive)

                if not matching_files:
                    formatter.error(f"No files matching '{internal_path}'")
                    return 1

                # Destination must be a directory for multi-file copy
                dest_dir = Path(dest_path)
                dest_dir.mkdir(parents=True, exist_ok=True)

                if not dest_dir.is_dir():
                    formatter.error(f"Destination must be a directory for wildcard copy: {dest_path}")
                    return 1

                total_files = 0
                total_bytes = 0
                copied_files = []

                for rel_path, entry in matching_files:
                    # Build destination path, preserving subdirectory structure
                    dest_item = dest_dir / rel_path.replace('\\', os.sep)

                    if entry.is_directory:
                        # Create the directory
                        dest_item.mkdir(parents=True, exist_ok=True)
                        if not formatter.json_mode:
                            print(f"  {rel_path}\\ -> {dest_item}\\ (directory)")
                        continue

                    # Ensure parent directory exists
                    dest_item.parent.mkdir(parents=True, exist_ok=True)

                    # Read and write the file
                    if '\\' in rel_path:
                        read_path = rel_path.split('\\')
                    else:
                        read_path = [rel_path]

                    data = volume.read_file(read_path)
                    dest_item.write_bytes(data)

                    total_files += 1
                    total_bytes += len(data)
                    copied_files.append({
                        "name": rel_path,
                        "size": len(data),
                        "dest": str(dest_item)
                    })

                    if not formatter.json_mode:
                        print(f"  {rel_path} -> {dest_item} ({len(data):,} bytes)")

                formatter.success(
                    f"Copied {total_files} file(s), {total_bytes:,} bytes total",
                    source=source_display,
                    dest=dest_path,
                    files=total_files,
                    bytes=total_bytes,
                    copied=copied_files
                )

            else:
                # Single file copy
                data = volume.read_file(path_components)

                # Check if dest is a directory
                dest = Path(dest_path)
                if dest.is_dir():
                    dest = dest / path_components[-1]
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)

                dest.write_bytes(data)

                formatter.success(
                    f"Copied {len(data):,} bytes",
                    source=source_display,
                    dest=str(dest),
                    bytes=len(data)
                )
        finally:
            disk.close()

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def copy_to_image(
    source_path: str,
    image_path: str,
    partition: int | None,
    internal_path: str,
    formatter: OutputFormatter,
    recursive: bool = False
) -> int:
    """Copy file or directory from filesystem to disk image.

    If the destination path ends with \\ or is an existing directory,
    the source filename will be appended automatically.
    """
    try:
        source = Path(source_path)
        if not source.exists():
            formatter.error(f"Source not found: {source_path}")
            return 1

        image_type = detect_image_type(image_path)

        if image_type == 'harddisk':
            if partition is None:
                formatter.error("Partition number required for hard disk image (e.g., image.img:0:\\FILE)")
                return 1
            disk = V9KHardDiskImage(image_path, readonly=False)
            volume = disk.get_partition(partition)
        elif image_type == 'ibmpc':
            disk = IBMPCDiskImage(image_path, readonly=False)
            volume = disk
        elif image_type == 'cpm':
            disk = V9KCPMDiskImage(image_path, readonly=False)
            volume = disk
        else:
            disk = V9KDiskImage(image_path, readonly=False)
            volume = disk

        try:
            # Parse the destination path
            path_components = split_internal_path(internal_path)

            # Check if destination looks like a directory (ends with \ or /)
            dest_is_dir = internal_path.endswith('\\') or internal_path.endswith('/')

            # If not explicitly a directory path, check if it's an existing directory
            if not dest_is_dir and path_components:
                try:
                    entry = volume.find_entry(path_components)
                    if entry and entry.is_directory:
                        dest_is_dir = True
                except Exception:
                    pass  # Not found or not a directory

            # If destination is a directory, append source filename
            if dest_is_dir:
                # Get the source filename and convert to DOS 8.3 format
                src_name = source.name.upper()
                try:
                    name, ext = validate_filename(src_name)
                    dos_name = name.rstrip() + ('.' + ext.rstrip() if ext.rstrip() else '')
                except Exception:
                    # Fallback: truncate to 8.3
                    if '.' in src_name:
                        parts = src_name.rsplit('.', 1)
                        dos_name = parts[0][:8] + '.' + parts[1][:3]
                    else:
                        dos_name = src_name[:8]
                path_components.append(dos_name)

            if not path_components:
                formatter.error("No destination specified in image path")
                return 1

            # Build display path
            final_internal_path = '\\'.join(path_components)
            if image_type == 'harddisk':
                dest_display = f"{image_path}:{partition}:\\{final_internal_path}"
            else:
                dest_display = f"{image_path}:\\{final_internal_path}"

            if source.is_dir():
                if not recursive:
                    formatter.error(f"'{source_path}' is a directory. Use -r for recursive copy.")
                    return 1

                # Recursive directory copy
                total_files, total_bytes = _copy_dir_to_image(
                    source, volume, path_components, formatter
                )

                formatter.success(
                    f"Copied {total_files} file(s), {total_bytes:,} bytes total",
                    source=source_path,
                    dest=dest_display,
                    files=total_files,
                    bytes=total_bytes
                )
            else:
                # Single file copy
                data = source.read_bytes()
                volume.write_file(path_components, data)

                formatter.success(
                    f"Copied {len(data):,} bytes",
                    source=source_path,
                    dest=dest_display,
                    bytes=len(data)
                )
        finally:
            disk.close()

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def _copy_dir_to_image(
    source_dir: Path,
    volume,
    dest_path_components: list[str],
    formatter: OutputFormatter
) -> tuple[int, int]:
    """
    Recursively copy a directory to a disk image.

    Args:
        source_dir: Source directory path
        volume: Disk volume to copy to
        dest_path_components: Destination path on disk
        formatter: Output formatter

    Returns:
        (total_files, total_bytes) copied
    """
    total_files = 0
    total_bytes = 0

    # Create the destination directory
    volume.create_directory(dest_path_components)

    # Iterate through source directory
    for item in source_dir.iterdir():
        # Convert filename to DOS 8.3 format (uppercase, truncate if needed)
        dos_name = item.name.upper()
        if len(dos_name) > 12:  # Max 8.3 = 12 chars with dot
            # Truncate name
            if '.' in dos_name:
                name_part, ext_part = dos_name.rsplit('.', 1)
                dos_name = name_part[:8] + '.' + ext_part[:3]
            else:
                dos_name = dos_name[:8]

        item_dest = dest_path_components + [dos_name]

        if item.is_dir():
            # Recurse into subdirectory
            sub_files, sub_bytes = _copy_dir_to_image(item, volume, item_dest, formatter)
            total_files += sub_files
            total_bytes += sub_bytes
        elif item.is_file():
            # Copy file
            try:
                data = item.read_bytes()
                volume.write_file(item_dest, data)
                total_files += 1
                total_bytes += len(data)

                if not formatter.json_mode:
                    dest_str = '\\'.join(item_dest)
                    print(f"  {item} -> {dest_str} ({len(data):,} bytes)")
            except Exception as e:
                if not formatter.json_mode:
                    print(f"  Warning: Failed to copy {item}: {e}")

    return total_files, total_bytes


def cmd_delete(args, formatter: OutputFormatter) -> int:
    """Handle the 'delete' command."""
    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None or internal_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    recursive = getattr(args, 'recursive', False)

    try:
        path_components = split_internal_path(internal_path)
        if not path_components:
            formatter.error("No file or directory specified to delete")
            return 1

        image_type = detect_image_type(image_path)

        if image_type == 'harddisk':
            if partition is None:
                formatter.error("Partition number required for hard disk image (e.g., image.img:0:\\FILE)")
                return 1
            disk = V9KHardDiskImage(image_path, readonly=False)
            volume = disk.get_partition(partition)
            delete_display = f"{image_path}:{partition}:\\{internal_path}"
        elif image_type == 'ibmpc':
            disk = IBMPCDiskImage(image_path, readonly=False)
            volume = disk
            delete_display = f"{image_path}:\\{internal_path}"
        elif image_type == 'cpm':
            disk = V9KCPMDiskImage(image_path, readonly=False)
            volume = disk
            delete_display = f"{image_path}:\\{internal_path}"
        else:
            disk = V9KDiskImage(image_path, readonly=False)
            volume = disk
            delete_display = f"{image_path}:\\{internal_path}"

        try:
            # Check if it's a directory
            is_directory = False
            try:
                entry = volume.find_entry(path_components)
                if entry and entry.is_directory:
                    is_directory = True
            except Exception:
                pass

            if is_directory:
                # Delete directory
                volume.delete_directory(path_components, recursive=recursive)
                formatter.success(
                    f"Deleted directory {internal_path}",
                    deleted=delete_display
                )
            else:
                # Delete file
                volume.delete_file(path_components)
                formatter.success(
                    f"Deleted {internal_path}",
                    deleted=delete_display
                )
        finally:
            disk.close()

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def cmd_verify(args, formatter: OutputFormatter) -> int:
    """Handle the 'verify' command."""
    from .verify import verify_disk, format_verification_result

    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    try:
        image_type = detect_image_type(image_path)
        verbose = getattr(args, 'verbose', False)

        if image_type == 'harddisk':
            with V9KHardDiskImage(image_path, readonly=True) as disk:
                if partition is not None:
                    # Verify specific partition
                    volume = disk.get_partition(partition)
                    result = verify_disk(volume, verbose=verbose)
                else:
                    # Verify entire hard disk
                    result = verify_disk(disk, verbose=verbose)

                if formatter.json_mode:
                    formatter.success(
                        "Verification complete",
                        valid=result.is_valid,
                        errors=result.errors,
                        warnings=result.warnings,
                        files_checked=result.files_checked,
                        directories_checked=result.directories_checked,
                        lost_clusters=result.lost_clusters,
                        bad_clusters=result.bad_clusters
                    )
                else:
                    print(format_verification_result(result))

        elif image_type == 'ibmpc':
            with IBMPCDiskImage(image_path, readonly=True) as disk:
                result = verify_disk(disk, verbose=verbose)
                if formatter.json_mode:
                    formatter.success(
                        "Verification complete",
                        valid=result.is_valid,
                        errors=result.errors,
                        warnings=result.warnings,
                        files_checked=result.files_checked,
                        lost_clusters=result.lost_clusters
                    )
                else:
                    print(format_verification_result(result))

        elif image_type == 'cpm':
            with V9KCPMDiskImage(image_path, readonly=True) as disk:
                result = verify_disk(disk, verbose=verbose)
                if formatter.json_mode:
                    formatter.success(
                        "Verification complete",
                        valid=result.is_valid,
                        errors=result.errors,
                        warnings=result.warnings,
                        files_checked=result.files_checked
                    )
                else:
                    print(format_verification_result(result))

        else:
            with V9KDiskImage(image_path, readonly=True) as disk:
                result = verify_disk(disk, verbose=verbose)
                if formatter.json_mode:
                    formatter.success(
                        "Verification complete",
                        valid=result.is_valid,
                        errors=result.errors,
                        warnings=result.warnings,
                        files_checked=result.files_checked,
                        lost_clusters=result.lost_clusters
                    )
                else:
                    print(format_verification_result(result))

        return 0 if result.is_valid else 1

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def cmd_create(args, formatter: OutputFormatter) -> int:
    """Handle the 'create' command."""
    import os
    from .creator import create_victor_floppy, create_ibm_floppy

    output_path = args.output

    # Check if file already exists
    if os.path.exists(output_path) and not getattr(args, 'force', False):
        formatter.error(f"File already exists: {output_path}. Use --force to overwrite.")
        return 1

    try:
        disk_type = args.type
        label = getattr(args, 'label', None)

        if disk_type == 'victor-ss':
            create_victor_floppy(output_path, sides='single', volume_label=label)
            formatter.success(f"Created Victor 9000 single-sided floppy: {output_path}")
        elif disk_type == 'victor-ds':
            create_victor_floppy(output_path, sides='double', volume_label=label)
            formatter.success(f"Created Victor 9000 double-sided floppy: {output_path}")
        elif disk_type in ('360K', '720K', '1.2M', '1.44M'):
            create_ibm_floppy(output_path, format=disk_type, volume_label=label)
            formatter.success(f"Created IBM PC {disk_type} floppy: {output_path}")
        else:
            formatter.error(f"Unknown disk type: {disk_type}")
            return 1

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def cmd_info(args, formatter: OutputFormatter) -> int:
    """Handle the 'info' command."""
    from .info import get_disk_info, format_disk_info

    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    try:
        image_type = detect_image_type(image_path)

        if image_type == 'harddisk':
            with V9KHardDiskImage(image_path, readonly=True) as disk:
                if partition is not None:
                    # Info for specific partition
                    volume = disk.get_partition(partition)
                    info = get_disk_info(volume)
                    info['partition'] = partition
                    info['name'] = volume.volume_label.volume_name.strip()
                else:
                    # Info for entire hard disk
                    info = get_disk_info(disk)

                if formatter.json_mode:
                    formatter.success("Disk information", **info)
                else:
                    verbose = getattr(args, 'verbose', False)
                    print(format_disk_info(info, verbose=verbose))

        elif image_type == 'ibmpc':
            with IBMPCDiskImage(image_path, readonly=True) as disk:
                info = get_disk_info(disk)
                if formatter.json_mode:
                    formatter.success("Disk information", **info)
                else:
                    verbose = getattr(args, 'verbose', False)
                    print(format_disk_info(info, verbose=verbose))

        elif image_type == 'cpm':
            with V9KCPMDiskImage(image_path, readonly=True) as disk:
                info = get_disk_info(disk)
                if formatter.json_mode:
                    formatter.success("Disk information", **info)
                else:
                    verbose = getattr(args, 'verbose', False)
                    print(format_disk_info(info, verbose=verbose))

        else:
            with V9KDiskImage(image_path, readonly=True) as disk:
                info = get_disk_info(disk)
                if formatter.json_mode:
                    formatter.success("Disk information", **info)
                else:
                    verbose = getattr(args, 'verbose', False)
                    print(format_disk_info(info, verbose=verbose))

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def cmd_attr(args, formatter: OutputFormatter) -> int:
    """Handle the 'attr' command - view or modify file attributes."""
    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    if not internal_path:
        formatter.error("No file specified. Use image.img:\\FILE or image.img:N:\\FILE")
        return 1

    try:
        path_components = split_internal_path(internal_path)
        if not path_components:
            formatter.error("No file specified")
            return 1

        image_type = detect_image_type(image_path)

        # Parse attribute modifications
        modifications = getattr(args, 'modifications', []) or []
        has_mods = len(modifications) > 0

        if image_type == 'cpm':
            formatter.error("CP/M disks do not support DOS file attributes")
            return 1

        # Open disk in appropriate mode
        readonly = not has_mods

        if image_type == 'harddisk':
            if partition is None:
                formatter.error("Partition number required for hard disk (e.g., image.img:0:\\FILE)")
                return 1
            disk = V9KHardDiskImage(image_path, readonly=readonly)
            volume = disk.get_partition(partition)
            display_path = f"{image_path}:{partition}:\\{internal_path}"
        elif image_type == 'ibmpc':
            disk = IBMPCDiskImage(image_path, readonly=readonly)
            volume = disk
            display_path = f"{image_path}:\\{internal_path}"
        else:
            disk = V9KDiskImage(image_path, readonly=readonly)
            volume = disk
            display_path = f"{image_path}:\\{internal_path}"

        try:
            # Get current attributes
            current_attrs = volume.get_attributes(path_components)

            if has_mods:
                # Apply modifications
                new_attrs = _apply_attr_modifications(current_attrs, modifications)
                volume.set_attributes(path_components, new_attrs)
                volume.flush()

                old_str = _format_attributes(current_attrs)
                new_str = _format_attributes(new_attrs)

                if formatter.json_mode:
                    formatter.success(
                        f"Updated attributes for {internal_path}",
                        file=display_path,
                        old_attributes=old_str,
                        new_attributes=new_str
                    )
                else:
                    print(f"{internal_path}: {old_str} -> {new_str}")
            else:
                # Just display current attributes
                attr_str = _format_attributes(current_attrs)
                if formatter.json_mode:
                    formatter.success(
                        f"Attributes for {internal_path}",
                        file=display_path,
                        attributes=attr_str,
                        readonly=bool(current_attrs & ATTR_READONLY),
                        hidden=bool(current_attrs & ATTR_HIDDEN),
                        system=bool(current_attrs & ATTR_SYSTEM),
                        archive=bool(current_attrs & ATTR_ARCHIVE)
                    )
                else:
                    print(f"{internal_path}: {attr_str}")

        finally:
            disk.close()

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def _format_attributes(attrs: int) -> str:
    """Format attributes as a string like 'R---' or '-HS-'."""
    result = ''
    result += 'R' if attrs & ATTR_READONLY else '-'
    result += 'H' if attrs & ATTR_HIDDEN else '-'
    result += 'S' if attrs & ATTR_SYSTEM else '-'
    result += 'A' if attrs & ATTR_ARCHIVE else '-'
    return result


def _apply_attr_modifications(current: int, modifications: list[str]) -> int:
    """
    Apply attribute modifications like +R, -A, etc.

    Args:
        current: Current attribute byte
        modifications: List of modifications like ['+R', '-A', '+H']

    Returns:
        New attribute byte
    """
    attrs = current

    attr_map = {
        'R': ATTR_READONLY,
        'H': ATTR_HIDDEN,
        'S': ATTR_SYSTEM,
        'A': ATTR_ARCHIVE,
    }

    for mod in modifications:
        if len(mod) < 2:
            continue

        op = mod[0]
        attr_char = mod[1].upper()

        if attr_char not in attr_map:
            continue

        attr_bit = attr_map[attr_char]

        if op == '+':
            attrs |= attr_bit
        elif op == '-':
            attrs &= ~attr_bit

    return attrs


EXTENDED_HELP = """
Victor 9000 Disk Image Utility - Detailed Help
===============================================

OVERVIEW
--------
This utility manages Victor 9000 floppy and hard disk images. It also supports
IBM PC floppy images. Features include reading, writing, and deleting files
using FAT12 and CP/M filesystems.

Supported disk types:
    - Victor 9000 floppy disks (single and double-sided)
    - Victor 9000 hard disk images (multi-partition)
    - IBM PC floppy disks (360K, 720K, 1.2M, 1.44M)
    - Victor 9000 CP/M-86 floppy disks (read-only)

PATH SYNTAX
-----------
Floppy disk images:
    image.img                      Image file only (list root directory)
    image.img:\\                    Root directory
    image.img:\\FILE.COM            File in root directory
    image.img:\\SUBDIR              Subdirectory
    image.img:\\SUBDIR\\FILE.COM    File in subdirectory

Hard disk images (with partitions):
    image.img                      Image file only (list partitions)
    image.img:0:\\                  Root of partition 0
    image.img:0:\\FILE.COM          File in partition 0 root
    image.img:1:\\SUBDIR            Subdirectory in partition 1
    image.img:2:\\SUBDIR\\FILE.COM  File in subdirectory on partition 2

The image type (floppy vs hard disk) is auto-detected based on file size
and disk label structure.

COMMANDS
--------

info <path>
    Show disk image information including type, size, and free space.

        vtg_image_util info disk.img              # Floppy info
        vtg_image_util info hd.img                # Hard disk info (all partitions)
        vtg_image_util info hd.img:0              # Hard disk partition 0 info

    Options:
        -v, --verbose   Show technical details (FAT size, cluster info, etc.)
        --json          Output in JSON format

verify <path>
    Verify disk image integrity (check FAT, directory entries, etc.).

        vtg_image_util verify disk.img            # Verify floppy
        vtg_image_util verify hd.img              # Verify all hard disk partitions

    Options:
        --json          Output in JSON format

create -t <type> [-l <label>] [-f] <output>
    Create a new blank formatted disk image.

        vtg_image_util create -t victor-ds newdisk.img       # Victor double-sided
        vtg_image_util create -t victor-ss newdisk.img       # Victor single-sided
        vtg_image_util create -t 1.44M -l MYDISK floppy.img  # IBM PC 1.44MB
        vtg_image_util create -t 720K floppy.img             # IBM PC 720KB
        vtg_image_util create -t 360K floppy.img -f          # Overwrite existing

    Disk types:
        victor-ss   Victor 9000 single-sided (~600KB)
        victor-ds   Victor 9000 double-sided (~1.2MB)
        360K        IBM PC 360KB (5.25" DD)
        720K        IBM PC 720KB (3.5" DD)
        1.2M        IBM PC 1.2MB (5.25" HD)
        1.44M       IBM PC 1.44MB (3.5" HD)

    Options:
        -t, --type      Disk type (required)
        -l, --label     Volume label (up to 11 characters)
        -f, --force     Overwrite existing file
        --json          Output in JSON format

list <path> [-r]
    List directory contents or partitions.

    For floppy images:
        vtg_image_util list disk.img              # List root directory
        vtg_image_util list disk.img:\\SUBDIR     # List subdirectory
        vtg_image_util list disk.img -r           # List all files recursively

    For hard disk images:
        vtg_image_util list hd.img                # List partitions
        vtg_image_util list hd.img:0:\\           # List partition 0 root
        vtg_image_util list hd.img:1:\\DOS        # List DOS dir on partition 1
        vtg_image_util list hd.img:0:\\ -r        # List partition 0 recursively

    Options:
        -r, --recursive List subdirectories recursively
        --json          Output in JSON format

copy <source> <dest> [-r]
    Copy files between disk image and local filesystem.

    Copy FROM image (floppy):
        vtg_image_util copy disk.img:\\FILE.COM .             # Single file
        vtg_image_util copy disk.img:\\*.COM c:\\temp\\       # Wildcard
        vtg_image_util copy disk.img:\\* c:\\temp\\ -r        # Recursive with subdirs

    Copy FROM image (hard disk):
        vtg_image_util copy hd.img:0:\\FILE.COM .             # From partition 0
        vtg_image_util copy hd.img:1:\\*.* c:\\temp\\         # Wildcard from partition 1

    Copy TO image:
        vtg_image_util copy file.txt disk.img:\\FILE.TXT     # To floppy
        vtg_image_util copy file.txt hd.img:0:\\FILE.TXT     # To partition 0
        vtg_image_util copy c:\\data\\*.txt disk.img:\\       # Multiple files

    Options:
        -r, --recursive Copy subdirectories recursively
        --json          Output in JSON format

delete <path> [-r]
    Delete a file or directory from the disk image.

        vtg_image_util delete disk.img:\\FILE.COM            # Delete file
        vtg_image_util delete hd.img:0:\\FILE.COM            # From partition 0
        vtg_image_util delete disk.img:\\SUBDIR -r           # Delete dir recursively

    Options:
        -r, --recursive Delete directories and all contents
        --json          Output in JSON format

mkdir <path>
    Create a directory on the disk image.

        vtg_image_util mkdir disk.img:\\NEWDIR               # Create in root
        vtg_image_util mkdir disk.img:\\PARENT\\CHILD        # Create nested
        vtg_image_util mkdir hd.img:0:\\NEWDIR               # On partition 0

    Options:
        --json          Output in JSON format

rmdir <path> [-r]
    Remove a directory from the disk image.

        vtg_image_util rmdir disk.img:\\EMPTYDIR             # Remove empty dir
        vtg_image_util rmdir disk.img:\\FULLDIR -r           # Remove with contents
        vtg_image_util rmdir hd.img:0:\\MYDIR -r             # From partition 0

    Options:
        -r, --recursive Remove directory and all contents
        --json          Output in JSON format

attr <path> [+/-RHSA]
    View or modify file attributes.

    View attributes:
        vtg_image_util attr disk.img:\\FILE.COM              # Show attributes

    Modify attributes:
        vtg_image_util attr disk.img:\\FILE.COM -- +R        # Set read-only
        vtg_image_util attr disk.img:\\FILE.COM -- -R +H     # Clear R, set H
        vtg_image_util attr disk.img:\\FILE.COM -- +R +H +S  # Set multiple

    Attributes:
        R = Read-only       H = Hidden
        S = System          A = Archive

    Note: Use -- before attribute flags to prevent shell interpretation.

    Options:
        --json          Output in JSON format

GLOBAL OPTIONS
--------------
    -h, --help      Show help message
    --help-syntax   Show this detailed help page
    --version       Show version number
    -v, --verbose   Show detailed/technical output
    -q, --quiet     Suppress non-essential output
    --json          Output in JSON format (for scripting)

WILDCARDS
---------
The copy command supports DOS-style wildcards:
    *       Matches any characters (including none)
    ?       Matches exactly one character

Examples:
    *.COM       All .COM files
    *.          All files without extension
    *.*         All files with extensions
    *           All files (with or without extension)
    FILE?.TXT   FILE1.TXT, FILE2.TXT, etc.

FILENAME FORMAT
---------------
Victor 9000 uses standard 8.3 DOS filenames:
    - Filename: 1-8 characters
    - Extension: 0-3 characters (optional)
    - Valid characters: A-Z, 0-9, ! # $ % & ' ( ) - @ ^ _ ` { } ~
    - Filenames are case-insensitive (stored uppercase)

JSON OUTPUT
-----------
Use --json for machine-readable output. All commands support JSON mode.
Errors are returned as: {"error": "message"}
Success includes relevant data fields depending on the command.

Example:
    vtg_image_util list disk.img --json | jq '.files[].name'

TECHNICAL NOTES
---------------
Victor 9000 FAT12 Floppy Disks:
    - 4 sectors per cluster (2048 bytes)
    - Single-sided: ~600KB, Double-sided: ~1.2MB
    - FAT at sectors 1-2 (SS) or 1-4 (DS)
    - Directory at sectors 3-10 (SS) or 5-12 (DS)

IBM PC FAT12 Floppy Disks:
    - Variable sectors per cluster (1-2)
    - Supports 360KB, 720KB, 1.2MB, 1.44MB formats
    - Auto-detected via BIOS Parameter Block (BPB)
    - Boot signature 0x55AA at offset 0x1FE

Victor 9000 CP/M-86 Floppy Disks:
    - 1024-byte allocation blocks (2 sectors)
    - Directory at sector 94 (after system tracks)
    - No subdirectories supported
    - Files displayed with user number column

Victor 9000 Hard Disks:
    - Physical disk label at sector 0
    - Multiple partitions (virtual volumes)
    - Variable cluster size (typically 64 sectors = 32KB)
    - Each partition has its own FAT and directory

EXIT CODES
----------
    0   Success
    1   Error (message printed to stderr or JSON output)

EXAMPLES
--------
# Create a new Victor disk and add files
vtg_image_util create -t victor-ds mydisk.img -l BACKUP
vtg_image_util copy *.COM mydisk.img:\\
vtg_image_util mkdir mydisk.img:\\DATA
vtg_image_util copy data.txt mydisk.img:\\DATA\\DATA.TXT
vtg_image_util list mydisk.img -r

# Extract all files from a hard disk partition
vtg_image_util list harddisk.img                          # See partitions
vtg_image_util copy harddisk.img:0:\\* c:\\backup\\ -r     # Extract partition 0

# Check disk integrity
vtg_image_util verify mydisk.img
vtg_image_util info mydisk.img -v
"""


def print_extended_help() -> None:
    """Print extended help documentation."""
    print(EXTENDED_HELP)


def cmd_mkdir(args, formatter: OutputFormatter) -> int:
    """Handle the 'mkdir' command - create a directory on disk image."""
    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    if not internal_path:
        formatter.error("No directory name specified. Use image.img:\\DIRNAME or image.img:N:\\DIRNAME")
        return 1

    try:
        path_components = split_internal_path(internal_path)
        if not path_components:
            formatter.error("No directory name specified")
            return 1

        image_type = detect_image_type(image_path)

        if image_type == 'cpm':
            formatter.error("CP/M disks do not support subdirectories")
            return 1

        if image_type == 'harddisk':
            if partition is None:
                formatter.error("Partition number required for hard disk (e.g., image.img:0:\\DIRNAME)")
                return 1
            disk = V9KHardDiskImage(image_path, readonly=False)
            volume = disk.get_partition(partition)
            display_path = f"{image_path}:{partition}:\\{internal_path}"
        elif image_type == 'ibmpc':
            disk = IBMPCDiskImage(image_path, readonly=False)
            volume = disk
            display_path = f"{image_path}:\\{internal_path}"
        else:
            disk = V9KDiskImage(image_path, readonly=False)
            volume = disk
            display_path = f"{image_path}:\\{internal_path}"

        try:
            volume.create_directory(path_components)
            volume.flush()

            formatter.success(
                f"Created directory {internal_path}",
                directory=display_path
            )
        finally:
            disk.close()

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1


def cmd_rmdir(args, formatter: OutputFormatter) -> int:
    """Handle the 'rmdir' command - remove a directory from disk image."""
    image_path, partition, internal_path = parse_image_path(args.path)

    if image_path is None:
        formatter.error(f"Invalid disk image path: {args.path}")
        return 1

    if not internal_path:
        formatter.error("No directory name specified. Use image.img:\\DIRNAME or image.img:N:\\DIRNAME")
        return 1

    try:
        path_components = split_internal_path(internal_path)
        if not path_components:
            formatter.error("No directory name specified")
            return 1

        image_type = detect_image_type(image_path)
        recursive = getattr(args, 'recursive', False)

        if image_type == 'cpm':
            formatter.error("CP/M disks do not support subdirectories")
            return 1

        if image_type == 'harddisk':
            if partition is None:
                formatter.error("Partition number required for hard disk (e.g., image.img:0:\\DIRNAME)")
                return 1
            disk = V9KHardDiskImage(image_path, readonly=False)
            volume = disk.get_partition(partition)
            display_path = f"{image_path}:{partition}:\\{internal_path}"
        elif image_type == 'ibmpc':
            disk = IBMPCDiskImage(image_path, readonly=False)
            volume = disk
            display_path = f"{image_path}:\\{internal_path}"
        else:
            disk = V9KDiskImage(image_path, readonly=False)
            volume = disk
            display_path = f"{image_path}:\\{internal_path}"

        try:
            volume.delete_directory(path_components, recursive=recursive)
            volume.flush()

            formatter.success(
                f"Removed directory {internal_path}",
                directory=display_path
            )
        finally:
            disk.close()

        return 0

    except V9KError as e:
        formatter.error(str(e))
        return 1
    except OSError as e:
        formatter.error(f"Filesystem error: {e}")
        return 1
