"""
Icon management for the GUI.

Uses wx.ArtProvider for standard icons with cross-platform native appearance.
"""

import wx


class IconManager:
    """Manages icons for the application using wx.ArtProvider."""

    # Icon size constants
    SIZE_SMALL = (16, 16)
    SIZE_TOOLBAR = (24, 24)
    SIZE_LARGE = (32, 32)

    def __init__(self):
        self._image_list_small: wx.ImageList | None = None
        self._image_list_large: wx.ImageList | None = None

        # Index mapping for small image list
        self.IDX_FILE = 0
        self.IDX_FOLDER = 1
        self.IDX_FOLDER_OPEN = 2
        self.IDX_PARENT = 3
        self.IDX_DISK = 4

    def get_small_image_list(self) -> wx.ImageList:
        """Get or create the small (16x16) image list for file lists."""
        if self._image_list_small is None:
            self._image_list_small = wx.ImageList(16, 16)

            # Add standard icons from ArtProvider
            self._image_list_small.Add(
                wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_LIST, self.SIZE_SMALL)
            )
            self._image_list_small.Add(
                wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_LIST, self.SIZE_SMALL)
            )
            self._image_list_small.Add(
                wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_LIST, self.SIZE_SMALL)
            )
            self._image_list_small.Add(
                wx.ArtProvider.GetBitmap(wx.ART_GO_UP, wx.ART_LIST, self.SIZE_SMALL)
            )
            self._image_list_small.Add(
                wx.ArtProvider.GetBitmap(wx.ART_HARDDISK, wx.ART_LIST, self.SIZE_SMALL)
            )

        return self._image_list_small

    def get_toolbar_bitmap(self, art_id: str) -> wx.Bitmap:
        """Get a toolbar-sized bitmap for the given art ID."""
        return wx.ArtProvider.GetBitmap(art_id, wx.ART_TOOLBAR, self.SIZE_TOOLBAR)

    def get_menu_bitmap(self, art_id: str) -> wx.Bitmap:
        """Get a menu-sized bitmap for the given art ID."""
        return wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, self.SIZE_SMALL)


# Standard art IDs used in the application
ART_OPEN = wx.ART_FILE_OPEN
ART_SAVE = wx.ART_FILE_SAVE
ART_UP = wx.ART_GO_UP
ART_REFRESH = wx.ART_REDO  # No standard refresh, use redo
ART_COPY = wx.ART_COPY
ART_DELETE = wx.ART_DELETE
ART_FOLDER = wx.ART_FOLDER
ART_FILE = wx.ART_NORMAL_FILE
ART_DISK = wx.ART_HARDDISK
ART_INFO = wx.ART_INFORMATION
ART_QUIT = wx.ART_QUIT
ART_PASTE = wx.ART_PASTE
ART_CLOSE = wx.ART_CLOSE


# Global icon manager instance
_icon_manager: IconManager | None = None


def get_icon_manager() -> IconManager:
    """Get the global icon manager instance."""
    global _icon_manager
    if _icon_manager is None:
        _icon_manager = IconManager()
    return _icon_manager
