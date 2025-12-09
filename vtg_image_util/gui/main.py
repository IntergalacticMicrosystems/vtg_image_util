"""
Main entry point for the GUI application.

Usage:
    python -m vtg_image_util.gui [disk_image.img]
    python -m vtg_image_util.gui [disk_image.img:partition]

Examples:
    python -m vtg_image_util.gui disk.img        # Open floppy image
    python -m vtg_image_util.gui vichd.img       # Open hard disk (prompts for partition)
    python -m vtg_image_util.gui vichd.img:0     # Open partition 0 directly
"""

import sys
import argparse
import re

import wx

from .main_frame import MainFrame


def parse_image_path(path: str) -> tuple[str, int | None]:
    """
    Parse an image path with optional partition notation.

    Args:
        path: Path like "disk.img" or "disk.img:0"

    Returns:
        Tuple of (image_path, partition_index or None)
    """
    # Check for partition notation at the end: image.img:N
    # Be careful not to match Windows drive letters like C:\path\file.img
    # Only match :N at the very end where N is a digit
    match = re.match(r'^(.+):(\d+)$', path)
    if match:
        image_path = match.group(1)
        partition_idx = int(match.group(2))
        return (image_path, partition_idx)

    return (path, None)


class DiskImageApp(wx.App):
    """Main application class."""

    def __init__(self, image_path: str | None = None, partition_idx: int | None = None):
        self._image_path = image_path
        self._partition_idx = partition_idx
        super().__init__()

    def OnInit(self):
        """Initialize the application."""
        # Create main frame
        self._frame = MainFrame()
        self._frame.Show()
        self.SetTopWindow(self._frame)

        # Open image if provided
        if self._image_path:
            # Use CallAfter to open after the window is fully initialized
            wx.CallAfter(self._frame.open_file, self._image_path, self._partition_idx)

        return True


def main(args: list[str] | None = None):
    """
    Main entry point for the GUI.

    Args:
        args: Command-line arguments (uses sys.argv if None)
    """
    parser = argparse.ArgumentParser(
        description="Vtg Disk Image Utility - GUI",
        prog="python -m vtg_image_util.gui"
    )
    parser.add_argument(
        "image",
        nargs="?",
        help="Disk image file to open (use image.img:N to specify partition)"
    )

    parsed = parser.parse_args(args)

    image_path = None
    partition_idx = None

    if parsed.image:
        image_path, partition_idx = parse_image_path(parsed.image)

    app = DiskImageApp(image_path=image_path, partition_idx=partition_idx)
    app.MainLoop()


if __name__ == "__main__":
    main()
