"""
Toolbar component for the main window.

Provides toolbar buttons for common operations.
"""

import wx

from .icons import (
    get_icon_manager,
    ART_OPEN, ART_SAVE, ART_CLOSE, ART_UP, ART_COPY, ART_PASTE, ART_DELETE, ART_REFRESH
)


# Toolbar button IDs
ID_OPEN = wx.ID_OPEN
ID_SAVE = wx.ID_SAVE
ID_CLOSE = wx.NewIdRef()
ID_UP = wx.NewIdRef()
ID_COPY_FROM = wx.NewIdRef()
ID_COPY_TO = wx.NewIdRef()
ID_DELETE = wx.ID_DELETE
ID_REFRESH = wx.ID_REFRESH


def create_toolbar(parent: wx.Frame) -> wx.ToolBar:
    """
    Create the main toolbar.

    Args:
        parent: The parent frame

    Returns:
        The created toolbar
    """
    toolbar = parent.CreateToolBar(
        style=wx.TB_HORIZONTAL | wx.TB_FLAT | wx.TB_TEXT
    )

    icon_mgr = get_icon_manager()

    # Open button
    toolbar.AddTool(
        ID_OPEN,
        "Open",
        icon_mgr.get_toolbar_bitmap(ART_OPEN),
        shortHelp="Open disk image (Ctrl+O)"
    )

    # Save button
    toolbar.AddTool(
        ID_SAVE,
        "Save",
        icon_mgr.get_toolbar_bitmap(ART_SAVE),
        shortHelp="Save changes (Ctrl+S)"
    )

    # Close button
    toolbar.AddTool(
        ID_CLOSE,
        "Close",
        icon_mgr.get_toolbar_bitmap(ART_CLOSE),
        shortHelp="Close disk image (Ctrl+W)"
    )

    toolbar.AddSeparator()

    # Navigation
    toolbar.AddTool(
        ID_UP,
        "Up",
        icon_mgr.get_toolbar_bitmap(ART_UP),
        shortHelp="Go to parent directory (Backspace)"
    )

    toolbar.AddSeparator()

    # File operations
    toolbar.AddTool(
        ID_COPY_FROM,
        "Copy From",
        icon_mgr.get_toolbar_bitmap(ART_COPY),
        shortHelp="Copy selected files to local disk"
    )

    toolbar.AddTool(
        ID_COPY_TO,
        "Copy To",
        icon_mgr.get_toolbar_bitmap(ART_PASTE),
        shortHelp="Copy local files to disk image"
    )

    toolbar.AddTool(
        ID_DELETE,
        "Delete",
        icon_mgr.get_toolbar_bitmap(ART_DELETE),
        shortHelp="Delete selected files (Delete)"
    )

    toolbar.AddSeparator()

    # Refresh
    toolbar.AddTool(
        ID_REFRESH,
        "Refresh",
        icon_mgr.get_toolbar_bitmap(ART_REFRESH),
        shortHelp="Refresh directory (F5)"
    )

    toolbar.Realize()
    return toolbar


def update_toolbar_state(
    toolbar: wx.ToolBar,
    has_disk: bool,
    has_selection: bool,
    is_dirty: bool = False,
    is_readonly: bool = False
):
    """
    Update toolbar button states based on current context.

    Args:
        toolbar: The toolbar to update
        has_disk: Whether a disk image is currently open
        has_selection: Whether any files are selected
        is_dirty: Whether there are unsaved changes
        is_readonly: Whether the disk is read-only
    """
    # Save requires disk, dirty, and not readonly
    toolbar.EnableTool(ID_SAVE, has_disk and is_dirty and not is_readonly)

    # Close requires disk
    toolbar.EnableTool(ID_CLOSE, has_disk)

    # Navigation requires disk
    toolbar.EnableTool(ID_UP, has_disk)

    # File operations require disk
    toolbar.EnableTool(ID_COPY_FROM, has_disk and has_selection)
    toolbar.EnableTool(ID_COPY_TO, has_disk and not is_readonly)
    toolbar.EnableTool(ID_DELETE, has_disk and has_selection and not is_readonly)
    toolbar.EnableTool(ID_REFRESH, has_disk)
