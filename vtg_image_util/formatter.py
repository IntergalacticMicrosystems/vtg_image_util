"""
Output formatting for Victor 9000 and IBM PC disk image utilities.
"""

import json
import sys

from .models import DirectoryEntry


class OutputFormatter:
    """Handle output formatting (text or JSON)."""

    def __init__(self, json_mode: bool = False):
        self.json_mode = json_mode

    def success(self, message: str, **data) -> None:
        """Output success message."""
        if self.json_mode:
            output = {"status": "success", "message": message, **data}
            print(json.dumps(output))
        else:
            print(message)

    def error(self, message: str) -> None:
        """Output error message."""
        if self.json_mode:
            output = {"status": "error", "message": message}
            print(json.dumps(output))
        else:
            print(f"Error: {message}", file=sys.stderr)

    def list_files(self, entries: list[DirectoryEntry], path: str = "") -> None:
        """Output file listing."""
        if self.json_mode:
            files = []
            for entry in entries:
                if not entry.is_dot_entry:
                    files.append({
                        "name": entry.full_name,
                        "size": entry.file_size,
                        "attr": entry.attr_string(),
                        "cluster": entry.first_cluster,
                        "is_directory": entry.is_directory
                    })
            output = {"status": "success", "path": path or "\\", "files": files}
            print(json.dumps(output))
        else:
            if path:
                print(f"Directory of {path}")
            else:
                print("Directory of \\")
            print()

            total_files = 0
            total_bytes = 0

            for entry in entries:
                if entry.is_dot_entry:
                    continue

                if entry.is_directory:
                    size_str = "<DIR>"
                else:
                    size_str = str(entry.file_size)
                    total_bytes += entry.file_size

                total_files += 1
                print(f"  {entry.full_name:<12}  {size_str:>10}  {entry.attr_string()}")

            print()
            print(f"  {total_files} file(s)  {total_bytes:,} bytes")

    def list_partitions(self, partitions: list[dict], image_path: str = "") -> None:
        """Output partition listing."""
        if self.json_mode:
            output = {
                "status": "success",
                "image": image_path,
                "partitions": partitions
            }
            print(json.dumps(output))
        else:
            print(f"Partitions in {image_path}:")
            print()
            for p in partitions:
                capacity_mb = p['capacity_bytes'] / (1024 * 1024)
                name = p['name'] if p['name'] else f"Volume {p['index']}"
                print(f"  {p['index']}: {name:<16} {capacity_mb:>8.1f} MB")
            print()
            print(f"  {len(partitions)} partition(s)")

    def list_cpm_files(self, files: list, path: str = "") -> None:
        """Output CP/M file listing with user numbers.

        Args:
            files: List of CPMFileInfo objects
            path: Display path
        """
        if self.json_mode:
            file_list = []
            for f in files:
                file_list.append({
                    "user": f.user,
                    "name": f.full_name,
                    "size": f.file_size,
                    "is_read_only": f.is_read_only,
                    "is_system": f.is_system
                })
            output = {"status": "success", "path": path or "\\", "files": file_list}
            print(json.dumps(output))
        else:
            if path:
                print(f"Directory of {path}")
            else:
                print("Directory of \\")
            print()

            # Header
            print(f"  {'User':>4}  {'Name':<12}  {'Size':>10}  Attr")

            total_files = 0
            total_bytes = 0

            for f in files:
                attrs = []
                if f.is_read_only:
                    attrs.append('R')
                if f.is_system:
                    attrs.append('S')
                attr_str = ''.join(attrs) if attrs else '-'

                print(f"  {f.user:>4}  {f.full_name:<12}  {f.file_size:>10,}  {attr_str}")
                total_files += 1
                total_bytes += f.file_size

            print()
            print(f"  {total_files} file(s)  {total_bytes:,} bytes")
