"""
Main entry point for the GUI application.

Usage:
    python -m vtg_image_util.gui [disk_image.img]
"""

import sys
import argparse

import wx

from .main_frame import MainFrame


class DiskImageApp(wx.App):
    """Main application class."""

    def __init__(self, image_path: str | None = None):
        self._image_path = image_path
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
            wx.CallAfter(self._frame.open_file, self._image_path)

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
        help="Disk image file to open"
    )

    parsed = parser.parse_args(args)

    app = DiskImageApp(image_path=parsed.image)
    app.MainLoop()


if __name__ == "__main__":
    main()
