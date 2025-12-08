"""
Drag and drop support for the GUI.

Provides drop target for importing files and drag source for exporting files.
"""

import os
import tempfile
from typing import Callable

import wx


class FileDropTarget(wx.FileDropTarget):
    """
    Drop target that accepts files dragged from the OS file manager.

    When files are dropped, calls the provided callback with the list of paths.
    """

    def __init__(self, callback: Callable[[list[str]], bool]):
        """
        Initialize the drop target.

        Args:
            callback: Function called with list of dropped file paths.
                     Should return True if files were accepted.
        """
        super().__init__()
        self._callback = callback

    def OnDropFiles(self, x: int, y: int, filenames: list[str]) -> bool:
        """Handle dropped files."""
        if self._callback:
            return self._callback(filenames)
        return False


class DragDropManager:
    """
    Manages drag and drop operations for the file list.

    Handles both dragging files out of the image (export) and
    dropping files into the image (import).
    """

    def __init__(self, parent: wx.Window):
        self._parent = parent
        self._temp_files: list[str] = []
        self._export_callback: Callable[[list[str]], list[str]] | None = None
        self._import_callback: Callable[[list[str]], bool] | None = None

    def set_export_callback(self, callback: Callable[[list[str]], list[str]]):
        """
        Set the callback for exporting files (drag out).

        Args:
            callback: Function that takes list of internal paths and returns
                     list of temporary file paths containing the exported data.
        """
        self._export_callback = callback

    def set_import_callback(self, callback: Callable[[list[str]], bool]):
        """
        Set the callback for importing files (drop in).

        Args:
            callback: Function that takes list of local file paths and
                     returns True if import was successful.
        """
        self._import_callback = callback

    def create_drop_target(self) -> FileDropTarget:
        """Create a drop target for the file list."""
        return FileDropTarget(self._on_drop)

    def start_drag(self, internal_paths: list[str]):
        """
        Start a drag operation for the given internal paths.

        Creates temporary files and initiates the drag.
        """
        if not self._export_callback or not internal_paths:
            return

        # Clean up any previous temp files
        self._cleanup_temp_files()

        try:
            # Export files to temp location
            temp_paths = self._export_callback(internal_paths)
            if not temp_paths:
                return

            self._temp_files = temp_paths

            # Create file data object with the temp files
            data = wx.FileDataObject()
            for path in temp_paths:
                data.AddFile(path)

            # Create and start the drag source
            drop_source = wx.DropSource(self._parent)
            drop_source.SetData(data)
            result = drop_source.DoDragDrop(wx.Drag_CopyOnly)

            # Note: We don't clean up temp files immediately because
            # the OS may still be copying them. They'll be cleaned up
            # on the next drag or when the manager is destroyed.

        except Exception as e:
            wx.MessageBox(
                f"Failed to start drag operation: {e}",
                "Drag Error",
                wx.OK | wx.ICON_ERROR,
                self._parent
            )

    def _on_drop(self, filenames: list[str]) -> bool:
        """Handle files dropped onto the control."""
        if not self._import_callback or not filenames:
            return False

        try:
            return self._import_callback(filenames)
        except Exception as e:
            wx.MessageBox(
                f"Failed to import files: {e}",
                "Drop Error",
                wx.OK | wx.ICON_ERROR,
                self._parent
            )
            return False

    def _cleanup_temp_files(self):
        """Clean up temporary files and directories from previous drag operations."""
        import shutil
        for path in self._temp_files:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                elif os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass  # Ignore cleanup errors
        self._temp_files = []

    def cleanup(self):
        """Clean up all resources."""
        self._cleanup_temp_files()


def create_temp_export_dir() -> str:
    """
    Create a temporary directory for exporting files.

    Returns:
        Path to the temporary directory.
    """
    return tempfile.mkdtemp(prefix="v9k_export_")
