"""
Main application window for the disk image utility.

Provides the primary UI including menu, toolbar, file list, and status bar.
"""

import os
import shutil
import tempfile
from typing import Any

import wx

from ..floppy import V9KDiskImage, IBMPCDiskImage
from ..harddisk import V9KHardDiskImage, V9KPartition
from ..cpm import V9KCPMDiskImage, CPMFileInfo
from ..info import get_disk_info
from ..models import DirectoryEntry
from ..utils import detect_image_type, validate_filename
from ..exceptions import V9KError

from .file_list import FileListPanel
from .toolbar import (
    create_toolbar, update_toolbar_state,
    ID_OPEN, ID_SAVE as ID_SAVE_TB, ID_CLOSE as ID_CLOSE_TB,
    ID_UP, ID_COPY_FROM, ID_COPY_TO, ID_DELETE, ID_REFRESH
)
from .dialogs import (
    ProgressDialog, PropertiesDialog, PartitionSelectDialog, AboutDialog
)
from .drag_drop import DragDropManager, FileDropTarget, create_temp_export_dir
from .preferences import get_preferences
from .preferences_dialog import PreferencesDialog


# Menu IDs
ID_SAVE = wx.NewIdRef()
ID_SAVE_CLOSE = wx.NewIdRef()
ID_CLOSE = wx.NewIdRef()
ID_COPY = wx.NewIdRef()
ID_PASTE = wx.NewIdRef()
ID_SELECT_ALL = wx.NewIdRef()
ID_PROPERTIES = wx.NewIdRef()
ID_PREFERENCES = wx.NewIdRef()
ID_RECENT_CLEAR = wx.NewIdRef()

# Recent file IDs (use a fixed range starting from a high ID)
ID_RECENT_BASE = wx.ID_HIGHEST + 100
ID_RECENT_MAX = 10


class MainFrame(wx.Frame):
    """Main application window."""

    def __init__(self):
        # Get preferences for window position
        self._prefs = get_preferences()
        x, y, width, height = self._prefs.get_window_position()

        super().__init__(
            None,
            title="Vtg Disk Image Utility",
            size=(width, height)
        )

        # Restore window position if saved
        if x >= 0 and y >= 0:
            self.SetPosition((x, y))

        # Application state
        self._image_path: str | None = None  # Original file path
        self._temp_path: str | None = None   # Temp working copy path
        self._image_type: str | None = None
        self._disk: V9KDiskImage | V9KHardDiskImage | V9KCPMDiskImage | None = None
        self._partition_idx: int | None = None
        self._current_path: list[str] = []
        self._readonly = False
        self._dirty = False  # True if unsaved changes exist
        self._recent_menu: wx.Menu | None = None
        # Clipboard for copy/paste: list of (path_components, entry) tuples
        self._clipboard: list[tuple[list[str], DirectoryEntry | CPMFileInfo]] = []

        # Create UI components
        self._create_menu()
        self._toolbar = create_toolbar(self)
        self._file_panel = FileListPanel(self)
        self._create_statusbar()

        # Set up drag and drop
        self._drag_manager = DragDropManager(self._file_panel.file_list)
        self._drag_manager.set_export_callback(self._export_files_for_drag)
        self._drag_manager.set_import_callback(self._import_dropped_files_at_pos)
        drop_target = self._drag_manager.create_drop_target()
        self._file_panel.file_list.SetDropTarget(drop_target)

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._file_panel, 1, wx.EXPAND)
        self.SetSizer(sizer)

        # Bind events
        self._bind_events()

        # Initial state
        self._update_ui_state()

        # Center on screen if no saved position
        if x < 0 or y < 0:
            self.Centre()

    def _create_menu(self):
        """Create the menu bar."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        file_menu.Append(ID_OPEN, "&Open...\tCtrl+O", "Open a disk image")
        file_menu.Append(ID_SAVE, "&Save\tCtrl+S", "Save changes to disk image")
        file_menu.Append(ID_SAVE_CLOSE, "Save && Close", "Save changes and close disk image")
        file_menu.Append(ID_CLOSE, "&Close\tCtrl+W", "Close current disk image")
        file_menu.AppendSeparator()

        # Recent Files submenu
        self._recent_menu = wx.Menu()
        self._update_recent_menu()
        file_menu.AppendSubMenu(self._recent_menu, "Recent &Files")

        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4", "Exit the application")
        menubar.Append(file_menu, "&File")

        # Edit menu
        edit_menu = wx.Menu()
        edit_menu.Append(ID_COPY, "&Copy\tCtrl+C", "Copy selected files to clipboard")
        edit_menu.Append(ID_PASTE, "&Paste\tCtrl+V", "Paste files from clipboard")
        edit_menu.AppendSeparator()
        edit_menu.Append(ID_SELECT_ALL, "Select &All\tCtrl+A", "Select all files")
        edit_menu.AppendSeparator()
        edit_menu.Append(ID_COPY_FROM, "Copy &From Image...\tCtrl+Shift+C",
                        "Copy selected files to local disk")
        edit_menu.Append(ID_COPY_TO, "Copy &To Image...\tCtrl+Shift+V",
                        "Copy local files to disk image")
        edit_menu.AppendSeparator()
        edit_menu.Append(ID_DELETE, "&Delete\tDelete", "Delete selected files")
        edit_menu.AppendSeparator()
        edit_menu.Append(ID_PROPERTIES, "P&roperties\tAlt+Enter",
                        "Show file properties")
        edit_menu.AppendSeparator()
        edit_menu.Append(ID_PREFERENCES, "Pr&eferences...", "Edit application settings")
        menubar.Append(edit_menu, "&Edit")

        # View menu
        view_menu = wx.Menu()
        view_menu.Append(ID_REFRESH, "&Refresh\tF5", "Refresh directory listing")
        view_menu.Append(ID_UP, "Go &Up\tBackspace", "Go to parent directory")
        menubar.Append(view_menu, "&View")

        # Help menu
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "&About...", "About this application")
        menubar.Append(help_menu, "&Help")

        self.SetMenuBar(menubar)

    def _create_statusbar(self):
        """Create the status bar."""
        self._statusbar = self.CreateStatusBar(3)
        self._statusbar.SetStatusWidths([-2, -1, -1])
        self._statusbar.SetStatusText("Ready", 0)
        self._statusbar.SetStatusText("", 1)
        self._statusbar.SetStatusText("", 2)

    def _update_recent_menu(self):
        """Update the recent files submenu."""
        if self._recent_menu is None:
            return

        # Clear existing items
        for item in list(self._recent_menu.GetMenuItems()):
            self._recent_menu.Delete(item)

        # Add recent files
        recent_files = self._prefs.get_recent_files()

        if recent_files:
            for i, filepath in enumerate(recent_files[:ID_RECENT_MAX]):
                # Create menu item with number prefix
                label = f"&{i + 1}. {os.path.basename(filepath)}"
                item_id = ID_RECENT_BASE + i
                self._recent_menu.Append(item_id, label, filepath)
                self.Bind(wx.EVT_MENU, self._on_recent_file, id=item_id)

            self._recent_menu.AppendSeparator()
            self._recent_menu.Append(ID_RECENT_CLEAR, "&Clear Recent Files")
            self.Bind(wx.EVT_MENU, self._on_clear_recent, id=ID_RECENT_CLEAR)
        else:
            # Show disabled "No recent files" item
            item = self._recent_menu.Append(wx.ID_ANY, "(No recent files)")
            item.Enable(False)

    def _bind_events(self):
        """Bind event handlers."""
        # Menu/toolbar events
        self.Bind(wx.EVT_MENU, self._on_open, id=ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_save, id=ID_SAVE)
        self.Bind(wx.EVT_MENU, self._on_save, id=ID_SAVE_TB)  # Toolbar save button
        self.Bind(wx.EVT_MENU, self._on_save_close, id=ID_SAVE_CLOSE)
        self.Bind(wx.EVT_MENU, self._on_close_image, id=ID_CLOSE)
        self.Bind(wx.EVT_MENU, self._on_close_image, id=ID_CLOSE_TB)  # Toolbar close button
        self.Bind(wx.EVT_MENU, self._on_exit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_copy, id=ID_COPY)
        self.Bind(wx.EVT_MENU, self._on_paste, id=ID_PASTE)
        self.Bind(wx.EVT_MENU, self._on_select_all, id=ID_SELECT_ALL)
        self.Bind(wx.EVT_MENU, self._on_copy_from, id=ID_COPY_FROM)
        self.Bind(wx.EVT_MENU, self._on_copy_to, id=ID_COPY_TO)
        self.Bind(wx.EVT_MENU, self._on_delete, id=ID_DELETE)
        self.Bind(wx.EVT_MENU, self._on_properties, id=ID_PROPERTIES)
        self.Bind(wx.EVT_MENU, self._on_preferences, id=ID_PREFERENCES)
        self.Bind(wx.EVT_MENU, self._on_refresh, id=ID_REFRESH)
        self.Bind(wx.EVT_MENU, self._on_up, id=ID_UP)
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)

        # File list events
        self._file_panel.file_list.Bind(
            wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated
        )
        self._file_panel.file_list.Bind(
            wx.EVT_LIST_ITEM_SELECTED, self._on_selection_changed
        )
        self._file_panel.file_list.Bind(
            wx.EVT_LIST_ITEM_DESELECTED, self._on_selection_changed
        )
        self._file_panel.file_list.Bind(
            wx.EVT_LIST_BEGIN_DRAG, self._on_begin_drag
        )
        self._file_panel.file_list.Bind(
            wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_context_menu
        )

        # Keyboard shortcuts
        self._file_panel.file_list.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

        # Window close
        self.Bind(wx.EVT_CLOSE, self._on_close_window)

    def _update_ui_state(self):
        """Update UI elements based on current state."""
        has_disk = self._disk is not None
        selected = self._file_panel.file_list.get_selected_entries()
        has_selection = len(selected) > 0

        update_toolbar_state(
            self._toolbar, has_disk, has_selection,
            is_dirty=self._dirty, is_readonly=self._readonly
        )

        # Update menu items
        menubar = self.GetMenuBar()
        menubar.Enable(ID_SAVE, has_disk and self._dirty and not self._readonly)
        menubar.Enable(ID_SAVE_CLOSE, has_disk and not self._readonly)
        menubar.Enable(ID_CLOSE, has_disk)
        menubar.Enable(ID_COPY, has_disk and has_selection)
        menubar.Enable(ID_PASTE, has_disk and not self._readonly and len(self._clipboard) > 0)
        menubar.Enable(ID_SELECT_ALL, has_disk)
        menubar.Enable(ID_COPY_FROM, has_disk and has_selection)
        menubar.Enable(ID_COPY_TO, has_disk and not self._readonly)
        menubar.Enable(ID_DELETE, has_disk and has_selection and not self._readonly)
        menubar.Enable(ID_PROPERTIES, has_disk and has_selection)
        menubar.Enable(ID_REFRESH, has_disk)
        menubar.Enable(ID_UP, has_disk and len(self._current_path) > 0)

        # Update status bar
        if has_disk:
            # Panel 0: Selection/file count info
            self._update_status_bar_info(selected)

            # Panel 1: Disk type
            self._statusbar.SetStatusText(self._get_disk_type_string(), 1)

            # Panel 2: Mode and free space
            disk = self._get_current_disk()
            try:
                info = get_disk_info(disk)
                free_text = info.get('free_formatted', '')
                mode_text = "Read-only" if self._readonly else "Read-write"
                if free_text:
                    self._statusbar.SetStatusText(f"{mode_text} | {free_text} free", 2)
                else:
                    self._statusbar.SetStatusText(mode_text, 2)
            except Exception:
                self._statusbar.SetStatusText(
                    "Read-only" if self._readonly else "Read-write", 2
                )
        else:
            self._statusbar.SetStatusText("", 1)
            self._statusbar.SetStatusText("", 2)

    def _update_status_bar_info(self, selected: list):
        """Update the first status bar panel with file/selection info."""
        total_items = self._file_panel.file_list.GetItemCount()
        parent_offset = 1 if self._file_panel.file_list._show_parent_entry else 0
        file_count = total_items - parent_offset

        num_selected = len(selected)

        if num_selected > 0:
            # Show selection count and total size
            total_size = 0
            for idx, entry in selected:
                if entry is not None:
                    if hasattr(entry, 'file_size'):
                        total_size += entry.file_size

            if total_size > 0:
                size_str = self._format_size(total_size)
                self._statusbar.SetStatusText(
                    f"{num_selected} selected ({size_str}) | {file_count} items", 0
                )
            else:
                self._statusbar.SetStatusText(
                    f"{num_selected} selected | {file_count} items", 0
                )
        else:
            self._statusbar.SetStatusText(f"{file_count} items", 0)

    def _format_size(self, size: int) -> str:
        """Format a size in bytes to human-readable string."""
        if size < 1024:
            return f"{size:,} bytes"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def _get_disk_type_string(self) -> str:
        """Get a human-readable disk type string."""
        if self._image_type == 'floppy':
            return "Victor 9000 Floppy"
        elif self._image_type == 'harddisk':
            return f"Victor 9000 Hard Disk (Partition {self._partition_idx})"
        elif self._image_type == 'ibmpc':
            return "IBM PC Floppy"
        elif self._image_type == 'cpm':
            return "Victor 9000 CP/M"
        return "Unknown"

    def _get_current_disk(self) -> Any:
        """Get the current disk or partition for operations."""
        if self._image_type == 'harddisk' and isinstance(self._disk, V9KHardDiskImage):
            return self._disk.get_partition(self._partition_idx)
        return self._disk

    def _build_path_display(self) -> str:
        """Build the path display string."""
        if not self._image_path:
            return "No disk image loaded"

        path = os.path.basename(self._image_path)
        if self._partition_idx is not None:
            path += f":{self._partition_idx}"
        path += ":\\"
        if self._current_path:
            path += "\\".join(self._current_path)
        return path

    def _refresh_file_list(self):
        """Refresh the current directory listing."""
        if not self._disk:
            self._file_panel.file_list.clear()
            self._file_panel.set_path("No disk image loaded")
            return

        try:
            disk = self._get_current_disk()

            if isinstance(disk, V9KCPMDiskImage):
                # CP/M doesn't have subdirectories
                files = disk.list_files()
                self._file_panel.file_list.set_entries(
                    files, show_parent=False, is_cpm=True
                )
            else:
                # FAT12 disk
                entries = disk.list_files(self._current_path if self._current_path else None)

                # Filter out volume labels and deleted entries
                visible_entries = [
                    e for e in entries
                    if not e.is_volume_label and not e.is_free and not e.is_dot_entry
                ]

                show_parent = len(self._current_path) > 0
                self._file_panel.file_list.set_entries(
                    visible_entries, show_parent=show_parent, is_cpm=False
                )

            self._file_panel.set_path(self._build_path_display())
            self._statusbar.SetStatusText("Ready", 0)

        except V9KError as e:
            wx.MessageBox(str(e), "Error", wx.OK | wx.ICON_ERROR, self)
            self._statusbar.SetStatusText(f"Error: {e}", 0)

    # Event handlers
    def _on_open(self, event):
        """Handle Open menu/toolbar action."""
        wildcard = (
            "Disk images (*.img;*.ima;*.dsk)|*.img;*.ima;*.dsk|"
            "All files (*.*)|*.*"
        )
        with wx.FileDialog(
            self,
            "Open Disk Image",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._open_image(dlg.GetPath())

    def _open_image(self, path: str, readonly: bool = False, partition_idx: int | None = None):
        """Open a disk image file.

        Args:
            path: Path to the disk image file
            readonly: Whether to open in read-only mode
            partition_idx: Optional partition index to open directly (for hard disks)
        """
        # Close any currently open image (will prompt to save if dirty)
        if not self._check_save_before_close():
            return  # User cancelled

        self._close_current_image()

        try:
            self._image_path = path
            self._image_type = detect_image_type(path)
            self._readonly = readonly
            self._dirty = False

            # Create temp copy to work with (unless readonly)
            if readonly:
                working_path = path
            else:
                # Create temp file with same extension
                ext = os.path.splitext(path)[1]
                fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="vtg_")
                os.close(fd)
                shutil.copy2(path, temp_path)
                self._temp_path = temp_path
                working_path = temp_path

            if self._image_type == 'harddisk':
                self._disk = V9KHardDiskImage(working_path, readonly=readonly)
                # Show partition selector - get full partition info
                partitions = self._disk.list_partitions()

                if len(partitions) == 0:
                    raise V9KError("No partitions found on hard disk")
                elif partition_idx is not None:
                    # Partition specified via command line - validate it
                    valid_indices = [p['index'] for p in partitions]
                    if partition_idx in valid_indices:
                        self._partition_idx = partition_idx
                    else:
                        raise V9KError(f"Invalid partition index {partition_idx}. "
                                      f"Valid partitions: {valid_indices}")
                elif len(partitions) == 1:
                    self._partition_idx = partitions[0]['index']
                else:
                    dlg = PartitionSelectDialog(self, partitions)
                    if dlg.ShowModal() == wx.ID_OK:
                        self._partition_idx = dlg.get_selected_partition()
                    else:
                        self._close_current_image()
                        return
                    dlg.Destroy()

            elif self._image_type == 'ibmpc':
                self._disk = IBMPCDiskImage(working_path, readonly=readonly)
            elif self._image_type == 'cpm':
                self._disk = V9KCPMDiskImage(working_path, readonly=readonly)
            else:  # Victor floppy
                self._disk = V9KDiskImage(working_path, readonly=readonly)

            self._current_path = []
            self._refresh_file_list()
            self._update_ui_state()

            self.SetTitle(f"Vtg Disk Image Utility - {os.path.basename(path)}")
            self._statusbar.SetStatusText(f"Opened: {path}", 0)

            # Add to recent files
            self._prefs.add_recent_file(path)
            self._update_recent_menu()

        except V9KError as e:
            wx.MessageBox(str(e), "Error Opening Image", wx.OK | wx.ICON_ERROR, self)
            self._close_current_image()
        except OSError as e:
            wx.MessageBox(
                f"Failed to open file: {e}",
                "Error Opening Image",
                wx.OK | wx.ICON_ERROR,
                self
            )
            self._close_current_image()

    def _close_current_image(self):
        """Close the currently open image and clean up temp file."""
        if self._disk:
            try:
                self._disk.close()
            except Exception:
                pass

        # Clean up temp file
        if self._temp_path and os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except OSError:
                pass

        self._disk = None
        self._image_path = None
        self._temp_path = None
        self._image_type = None
        self._partition_idx = None
        self._current_path = []
        self._dirty = False

    def _check_save_before_close(self) -> bool:
        """
        Check if there are unsaved changes and prompt user.

        Returns:
            True if it's okay to proceed (saved, discarded, or no changes)
            False if user cancelled the operation
        """
        if not self._dirty or self._readonly:
            return True

        result = wx.MessageBox(
            f"Save changes to '{os.path.basename(self._image_path)}'?",
            "Unsaved Changes",
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
            self
        )

        if result == wx.YES:
            return self._save_image()
        elif result == wx.NO:
            return True  # Discard changes
        else:
            return False  # Cancel

    def _save_image(self) -> bool:
        """
        Save changes by copying temp file back to original.

        Returns:
            True if save was successful
        """
        if not self._temp_path or not self._image_path:
            return False

        try:
            # Flush any pending changes in the disk object
            if self._disk:
                self._disk.flush()

            # Copy temp file back to original
            shutil.copy2(self._temp_path, self._image_path)
            self._dirty = False
            self._update_title()
            self._update_ui_state()
            self._statusbar.SetStatusText(f"Saved: {self._image_path}", 0)
            return True

        except OSError as e:
            wx.MessageBox(
                f"Failed to save file: {e}",
                "Save Error",
                wx.OK | wx.ICON_ERROR,
                self
            )
            return False

    def _on_save(self, event):
        """Handle Save menu action."""
        self._save_image()

    def _on_save_close(self, event):
        """Handle Save and Close menu action."""
        # Save if there are unsaved changes
        if self._dirty:
            if not self._save_image():
                return  # Save failed, don't close

        # Close the image
        self._close_current_image()
        self._refresh_file_list()
        self._update_ui_state()
        self.SetTitle("Vtg Disk Image Utility")
        self._statusbar.SetStatusText("Ready", 0)

    def _update_title(self):
        """Update window title to reflect current state."""
        if self._image_path:
            title = f"Vtg Disk Image Utility - {os.path.basename(self._image_path)}"
            if self._dirty:
                title += " *"
            self.SetTitle(title)
        else:
            self.SetTitle("Vtg Disk Image Utility")

    def _mark_dirty(self):
        """Mark the image as having unsaved changes."""
        if not self._readonly:
            self._dirty = True
            self._update_title()
            self._update_ui_state()

    def _on_close_image(self, event):
        """Handle Close menu action."""
        if not self._check_save_before_close():
            return  # User cancelled

        self._close_current_image()
        self._refresh_file_list()
        self._update_ui_state()
        self.SetTitle("Vtg Disk Image Utility")
        self._statusbar.SetStatusText("Ready", 0)

    def _on_exit(self, event):
        """Handle Exit menu action."""
        self.Close()

    def _on_close_window(self, event):
        """Handle window close."""
        # Check for unsaved changes
        if not self._check_save_before_close():
            event.Veto()  # Cancel close
            return

        # Save window position
        if not self.IsMaximized() and not self.IsIconized():
            pos = self.GetPosition()
            size = self.GetSize()
            self._prefs.save_window_position(pos.x, pos.y, size.width, size.height)

        self._close_current_image()
        self._drag_manager.cleanup()
        event.Skip()

    def _on_recent_file(self, event):
        """Handle selection of a recent file."""
        item_id = event.GetId()
        index = item_id - ID_RECENT_BASE
        recent_files = self._prefs.get_recent_files()

        if 0 <= index < len(recent_files):
            filepath = recent_files[index]
            if os.path.exists(filepath):
                self._open_image(filepath)
            else:
                wx.MessageBox(
                    f"File not found: {filepath}",
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                    self
                )
                # Remove from recent files and update menu
                recent = self._prefs.get_recent_files()
                if filepath in recent:
                    recent.remove(filepath)
                    self._prefs.set('recent_files', recent)
                self._update_recent_menu()

    def _on_clear_recent(self, event):
        """Handle clearing of recent files list."""
        self._prefs.clear_recent_files()
        self._update_recent_menu()

    def _on_refresh(self, event):
        """Handle Refresh action."""
        self._refresh_file_list()

    def _on_up(self, event):
        """Handle Up/parent directory action."""
        if self._current_path:
            self._current_path.pop()
            self._refresh_file_list()
            self._update_ui_state()

    def _on_item_activated(self, event):
        """Handle double-click on item."""
        index = event.GetIndex()
        entry = self._file_panel.file_list.get_entry_at(index)

        # Check for parent entry
        if entry is None and self._file_panel.file_list._show_parent_entry and index == 0:
            self._on_up(None)
            return

        if entry is None:
            return

        # Navigate into directory
        if isinstance(entry, DirectoryEntry) and entry.is_directory:
            self._current_path.append(entry.full_name)
            self._refresh_file_list()
            self._update_ui_state()

    def _on_selection_changed(self, event):
        """Handle selection change."""
        self._update_ui_state()
        event.Skip()

    def _on_key_down(self, event):
        """Handle keyboard shortcuts in file list."""
        keycode = event.GetKeyCode()

        if keycode == wx.WXK_BACK:
            self._on_up(None)
        elif keycode == wx.WXK_DELETE:
            self._on_delete(None)
        elif keycode == wx.WXK_F5:
            self._on_refresh(None)
        elif keycode == wx.WXK_RETURN and event.AltDown():
            self._on_properties(None)
        elif event.ControlDown():
            if keycode == ord('C'):
                self._on_copy(None)
            elif keycode == ord('V'):
                self._on_paste(None)
            elif keycode == ord('A'):
                self._on_select_all(None)
            else:
                event.Skip()
        else:
            event.Skip()

    def _on_context_menu(self, event):
        """Show context menu on right-click."""
        # Ensure the right-clicked item is selected
        item_idx = event.GetIndex()
        if item_idx >= 0:
            file_list = self._file_panel.file_list
            # If clicking on an unselected item, select only that item
            if not file_list.IsSelected(item_idx):
                # Deselect all first
                for i in range(file_list.GetItemCount()):
                    file_list.Select(i, on=False)
                # Select the clicked item
                file_list.Select(item_idx, on=True)

        menu = wx.Menu()

        menu.Append(ID_COPY, "Copy\tCtrl+C")
        menu.Append(ID_PASTE, "Paste\tCtrl+V")
        menu.AppendSeparator()
        menu.Append(ID_COPY_FROM, "Copy to Local...")
        menu.Append(ID_COPY_TO, "Copy from Local...")
        menu.AppendSeparator()
        menu.Append(ID_DELETE, "Delete")
        menu.AppendSeparator()
        menu.Append(ID_PROPERTIES, "Properties\tAlt+Enter")

        # Enable/disable based on state
        has_selection = len(self._file_panel.file_list.get_selected_entries()) > 0
        menu.Enable(ID_COPY, has_selection)
        menu.Enable(ID_PASTE, not self._readonly and len(self._clipboard) > 0)
        menu.Enable(ID_COPY_FROM, has_selection)
        menu.Enable(ID_DELETE, has_selection and not self._readonly)
        menu.Enable(ID_PROPERTIES, has_selection)

        self.PopupMenu(menu)
        menu.Destroy()

    def _on_copy(self, event):
        """Copy selected files/directories to clipboard."""
        if not self._disk:
            return

        selected = self._file_panel.file_list.get_selected_entries()
        if not selected:
            return

        # Build clipboard contents: (full_path_components, entry)
        self._clipboard = []
        for idx, entry in selected:
            if entry is not None:
                path = list(self._current_path)
                path.append(entry.full_name)
                self._clipboard.append((path, entry))

        if self._clipboard:
            count = len(self._clipboard)
            dirs = sum(1 for _, e in self._clipboard
                      if isinstance(e, DirectoryEntry) and e.is_directory)
            files = count - dirs
            parts = []
            if files > 0:
                parts.append(f"{files} file(s)")
            if dirs > 0:
                parts.append(f"{dirs} folder(s)")
            self._statusbar.SetStatusText(f"Copied {', '.join(parts)} to clipboard", 0)
            self._update_ui_state()

    def _on_paste(self, event):
        """Paste files/directories from clipboard to current directory."""
        if not self._disk or self._readonly or not self._clipboard:
            return

        disk = self._get_current_disk()

        # Check for existing files and collect overwrites
        existing_files = []
        for src_path, entry in self._clipboard:
            dest_name = entry.full_name
            # Check if file exists in current directory
            try:
                disk.find_entry(self._current_path + [dest_name])
                existing_files.append(dest_name)
            except Exception:
                pass  # File doesn't exist, OK to copy

        # Warn about overwrites (once for all files)
        if existing_files:
            if len(existing_files) == 1:
                msg = f"'{existing_files[0]}' already exists. Overwrite?"
            else:
                msg = f"{len(existing_files)} file(s) already exist:\n\n"
                msg += "\n".join(existing_files[:10])
                if len(existing_files) > 10:
                    msg += f"\n... and {len(existing_files) - 10} more"
                msg += "\n\nOverwrite all?"

            result = wx.MessageBox(
                msg,
                "Confirm Overwrite",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            if result != wx.YES:
                return

        # Perform the copy
        errors = []
        copied_files = 0
        copied_dirs = 0

        progress = ProgressDialog(
            "Pasting Files",
            "Preparing...",
            len(self._clipboard),
            self
        )

        try:
            for i, (src_path, entry) in enumerate(self._clipboard):
                dest_name = entry.full_name
                if not progress.update(i, f"Pasting {dest_name}..."):
                    break

                try:
                    if isinstance(entry, DirectoryEntry) and entry.is_directory:
                        # Copy directory recursively
                        dest_path = self._current_path + [dest_name]
                        self._paste_directory(disk, src_path, dest_path)
                        copied_dirs += 1
                    else:
                        # Copy file
                        data = disk.read_file(src_path)
                        dest_path = self._current_path + [dest_name]
                        disk.write_file(dest_path, data)
                        copied_files += 1
                except V9KError as e:
                    errors.append(f"{dest_name}: {e}")

        finally:
            progress.Destroy()

        # Refresh and update state
        self._refresh_file_list()
        if copied_files > 0 or copied_dirs > 0:
            self._mark_dirty()

        # Show result
        if errors:
            parts = []
            if copied_files > 0:
                parts.append(f"{copied_files} file(s)")
            if copied_dirs > 0:
                parts.append(f"{copied_dirs} folder(s)")
            msg = f"Pasted {', '.join(parts) if parts else '0 items'} with {len(errors)} error(s):\n\n"
            msg += "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... and {len(errors) - 10} more"
            wx.MessageBox(msg, "Paste Complete", wx.OK | wx.ICON_WARNING, self)
        else:
            parts = []
            if copied_files > 0:
                parts.append(f"{copied_files} file(s)")
            if copied_dirs > 0:
                parts.append(f"{copied_dirs} folder(s)")
            self._statusbar.SetStatusText(f"Pasted {', '.join(parts)}", 0)

    def _paste_directory(self, disk, src_path: list[str], dest_path: list[str]):
        """Recursively paste a directory."""
        # Create destination directory
        try:
            disk.create_directory(dest_path)
        except V9KError:
            pass  # May already exist

        # Copy contents
        entries = disk.list_files(src_path)
        for entry in entries:
            if entry.is_dot_entry or entry.is_volume_label:
                continue

            src_entry_path = src_path + [entry.full_name]
            dest_entry_path = dest_path + [entry.full_name]

            if entry.is_directory:
                self._paste_directory(disk, src_entry_path, dest_entry_path)
            else:
                data = disk.read_file(src_entry_path)
                disk.write_file(dest_entry_path, data)

    def _on_select_all(self, event):
        """Select all files in the file list."""
        if not self._disk:
            return

        file_list = self._file_panel.file_list
        count = file_list.GetItemCount()

        # Select all items
        for i in range(count):
            file_list.Select(i, on=True)

        self._update_ui_state()

    def _on_begin_drag(self, event):
        """Handle beginning of drag operation."""
        selected = self._file_panel.file_list.get_selected_entries()
        if not selected:
            return

        # Get paths of selected files and directories (excluding parent entry)
        paths = []
        for idx, entry in selected:
            if entry is not None:
                # Build full path
                full_path = list(self._current_path)
                full_path.append(entry.full_name)
                paths.append("\\".join(full_path))

        if paths:
            self._drag_manager.start_drag(paths)

    def _on_copy_from(self, event):
        """Copy selected files/directories from image to local disk."""
        selected = self._file_panel.file_list.get_selected_entries()
        if not selected:
            return

        # Filter out parent entry
        files_to_copy = [
            (idx, entry) for idx, entry in selected
            if entry is not None
        ]

        if not files_to_copy:
            return

        # Ask for destination directory
        with wx.DirDialog(
            self,
            "Select Destination Directory",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            dest_dir = dlg.GetPath()

        self._copy_files_from_image(files_to_copy, dest_dir, recursive=True)

    def _copy_files_from_image(
        self,
        files: list[tuple[int, DirectoryEntry | CPMFileInfo]],
        dest_dir: str,
        recursive: bool = False
    ):
        """Copy files and directories from the disk image to a local directory."""
        disk = self._get_current_disk()
        errors = []
        copied = 0
        dirs_created = 0

        progress = ProgressDialog(
            "Copying Files",
            "Preparing...",
            len(files),
            self
        )

        try:
            for i, (idx, entry) in enumerate(files):
                if not progress.update(i, f"Copying {entry.full_name}..."):
                    break  # Cancelled

                try:
                    # Build source path
                    source_path = list(self._current_path)
                    source_path.append(entry.full_name)

                    if isinstance(entry, DirectoryEntry) and entry.is_directory:
                        if recursive:
                            # Recursively copy directory
                            sub_copied, sub_dirs, sub_errors = self._copy_dir_from_image_recursive(
                                disk, source_path, dest_dir, entry.full_name
                            )
                            copied += sub_copied
                            dirs_created += sub_dirs
                            errors.extend(sub_errors)
                        else:
                            # Just create the directory
                            dir_path = os.path.join(dest_dir, entry.full_name)
                            os.makedirs(dir_path, exist_ok=True)
                            dirs_created += 1
                    else:
                        # Read file data
                        data = disk.read_file(source_path)

                        # Write to local disk
                        dest_path = os.path.join(dest_dir, entry.full_name)
                        with open(dest_path, 'wb') as f:
                            f.write(data)

                        copied += 1

                except V9KError as e:
                    errors.append(f"{entry.full_name}: {e}")
                except OSError as e:
                    errors.append(f"{entry.full_name}: {e}")

        finally:
            progress.Destroy()

        # Show result
        if errors:
            msg = f"Copied {copied} file(s)"
            if dirs_created > 0:
                msg += f", {dirs_created} folder(s)"
            msg += f" with {len(errors)} error(s):\n\n"
            msg += "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... and {len(errors) - 10} more errors"
            wx.MessageBox(msg, "Copy Complete", wx.OK | wx.ICON_WARNING, self)
        else:
            msg = f"Copied {copied} file(s)"
            if dirs_created > 0:
                msg += f", {dirs_created} folder(s)"
            self._statusbar.SetStatusText(msg, 0)

    def _copy_dir_from_image_recursive(
        self,
        disk,
        source_path: list[str],
        dest_base: str,
        rel_path: str
    ) -> tuple[int, int, list[str]]:
        """
        Recursively copy a directory from the disk image.

        Returns:
            (files_copied, dirs_created, errors)
        """
        copied = 0
        dirs_created = 0
        errors = []

        # Create the directory locally
        local_dir = os.path.join(dest_base, rel_path)
        try:
            os.makedirs(local_dir, exist_ok=True)
            dirs_created += 1
        except OSError as e:
            errors.append(f"{rel_path}: {e}")
            return copied, dirs_created, errors

        # List directory contents
        try:
            entries = disk.list_files(source_path)
        except V9KError as e:
            errors.append(f"{rel_path}: {e}")
            return copied, dirs_created, errors

        for entry in entries:
            if entry.is_dot_entry or entry.is_volume_label:
                continue

            entry_source = source_path + [entry.full_name]
            entry_rel = os.path.join(rel_path, entry.full_name)

            if entry.is_directory:
                # Recurse into subdirectory
                sub_copied, sub_dirs, sub_errors = self._copy_dir_from_image_recursive(
                    disk, entry_source, dest_base, entry_rel
                )
                copied += sub_copied
                dirs_created += sub_dirs
                errors.extend(sub_errors)
            else:
                # Copy file
                try:
                    data = disk.read_file(entry_source)
                    dest_path = os.path.join(dest_base, entry_rel)
                    with open(dest_path, 'wb') as f:
                        f.write(data)
                    copied += 1
                except V9KError as e:
                    errors.append(f"{entry_rel}: {e}")
                except OSError as e:
                    errors.append(f"{entry_rel}: {e}")

        return copied, dirs_created, errors

    def _on_copy_to(self, event):
        """Copy local files or directories to disk image."""
        if self._readonly:
            wx.MessageBox(
                "Disk image is read-only",
                "Cannot Copy",
                wx.OK | wx.ICON_WARNING,
                self
            )
            return

        # Ask user whether to copy files or a folder
        dlg = wx.MessageDialog(
            self,
            "What would you like to copy to the disk image?",
            "Copy To Image",
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
        )
        dlg.SetYesNoLabels("Files", "Folder")
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_CANCEL:
            return
        elif result == wx.ID_YES:
            # Copy files
            with wx.FileDialog(
                self,
                "Select Files to Copy",
                style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST
            ) as file_dlg:
                if file_dlg.ShowModal() != wx.ID_OK:
                    return
                source_paths = file_dlg.GetPaths()
            self._copy_files_to_image(source_paths)
        else:
            # Copy folder
            with wx.DirDialog(
                self,
                "Select Folder to Copy",
                style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
            ) as dir_dlg:
                if dir_dlg.ShowModal() != wx.ID_OK:
                    return
                source_dir = dir_dlg.GetPath()
            self._copy_dir_to_image(source_dir)

    def _copy_files_to_image(self, source_paths: list[str], target_path: list[str] | None = None):
        """Copy local files to the disk image.

        Args:
            source_paths: List of local file paths to copy
            target_path: Target directory path on disk (defaults to current path)
        """
        if self._readonly:
            return

        disk = self._get_current_disk()

        # Use current path if no target specified
        if target_path is None:
            target_path = list(self._current_path)

        # Check for existing files and warn about overwrites
        existing_files = []
        for source_path in source_paths:
            filename = os.path.basename(source_path)
            try:
                name, ext = validate_filename(filename)
                dest_name = name.rstrip() + ('.' + ext.rstrip() if ext.rstrip() else '')
            except Exception:
                dest_name = filename.upper()[:12]

            try:
                disk.find_entry(target_path + [dest_name])
                existing_files.append(dest_name)
            except Exception:
                pass  # File doesn't exist

        if existing_files:
            if len(existing_files) == 1:
                msg = f"'{existing_files[0]}' already exists. Overwrite?"
            else:
                msg = f"{len(existing_files)} file(s) already exist:\n\n"
                msg += "\n".join(existing_files[:10])
                if len(existing_files) > 10:
                    msg += f"\n... and {len(existing_files) - 10} more"
                msg += "\n\nOverwrite all?"

            result = wx.MessageBox(
                msg,
                "Confirm Overwrite",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            if result != wx.YES:
                return

        errors = []
        copied = 0

        progress = ProgressDialog(
            "Copying Files",
            "Preparing...",
            len(source_paths),
            self
        )

        try:
            for i, source_path in enumerate(source_paths):
                filename = os.path.basename(source_path)
                if not progress.update(i, f"Copying {filename}..."):
                    break  # Cancelled

                try:
                    # Validate and convert filename
                    try:
                        name, ext = validate_filename(filename)
                        dest_name = name.rstrip() + ('.' + ext.rstrip() if ext.rstrip() else '')
                    except Exception:
                        # Try using original name (might still work)
                        dest_name = filename.upper()[:12]

                    # Read local file
                    with open(source_path, 'rb') as f:
                        data = f.read()

                    # Build destination path
                    dest_path = list(target_path)
                    dest_path.append(dest_name)

                    # Write to disk image
                    disk.write_file(dest_path, data)
                    copied += 1

                except V9KError as e:
                    errors.append(f"{filename}: {e}")
                except OSError as e:
                    errors.append(f"{filename}: {e}")

        finally:
            progress.Destroy()

        # Refresh listing
        self._refresh_file_list()

        # Mark as dirty if any files were copied
        if copied > 0:
            self._mark_dirty()

        # Show result
        if errors:
            msg = f"Copied {copied} file(s) with {len(errors)} error(s):\n\n"
            msg += "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... and {len(errors) - 10} more errors"
            wx.MessageBox(msg, "Copy Complete", wx.OK | wx.ICON_WARNING, self)
        else:
            self._statusbar.SetStatusText(f"Copied {copied} file(s)", 0)

    def _copy_dir_to_image(self, source_dir: str, target_path: list[str] | None = None):
        """Copy a local directory (recursively) to the disk image.

        Args:
            source_dir: Local directory path to copy
            target_path: Target directory path on disk (defaults to current path)
        """
        if self._readonly:
            return

        disk = self._get_current_disk()

        # Use current path if no target specified
        if target_path is None:
            target_path = list(self._current_path)

        # Get the folder name and create it on the disk
        folder_name = os.path.basename(source_dir).upper()

        # Validate folder name for DOS 8.3 format
        try:
            name, ext = validate_filename(folder_name)
            dos_name = name.rstrip() + ('.' + ext.rstrip() if ext.rstrip() else '')
        except Exception:
            dos_name = folder_name[:8]  # Truncate to 8 chars

        # Build destination path (in target directory)
        dest_path = list(target_path) + [dos_name]

        # Check if directory already exists and warn
        try:
            entry = disk.find_entry(target_path + [dos_name])
            if entry:
                result = wx.MessageBox(
                    f"'{dos_name}' already exists. Files inside may be overwritten.\n\nContinue?",
                    "Confirm Overwrite",
                    wx.YES_NO | wx.ICON_QUESTION,
                    self
                )
                if result != wx.YES:
                    return
        except Exception:
            pass  # Directory doesn't exist, OK to create

        # Count total items for progress
        total_items = sum(1 for _ in self._count_items_recursive(source_dir))

        progress = ProgressDialog(
            "Copying Folder",
            f"Copying {folder_name}...",
            max(total_items, 1),
            self
        )

        errors = []
        copied = 0
        dirs_created = 0
        current_item = [0]  # Use list to allow modification in nested function

        try:
            # Create the top-level directory
            try:
                disk.create_directory(dest_path)
                dirs_created += 1
            except V9KError as e:
                # Directory might already exist
                if "exists" not in str(e).lower():
                    errors.append(f"{dos_name}: {e}")

            # Recursively copy contents
            self._copy_dir_contents_to_image(
                disk, source_dir, dest_path, progress, current_item, errors
            )
            copied = current_item[0]

        finally:
            progress.Destroy()

        # Refresh listing
        self._refresh_file_list()

        # Mark as dirty if anything was copied
        if copied > 0 or dirs_created > 0:
            self._mark_dirty()

        # Show result
        if errors:
            msg = f"Copied {copied} file(s), {dirs_created} folder(s) with {len(errors)} error(s):\n\n"
            msg += "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... and {len(errors) - 10} more errors"
            wx.MessageBox(msg, "Copy Complete", wx.OK | wx.ICON_WARNING, self)
        else:
            self._statusbar.SetStatusText(f"Copied {copied} file(s), {dirs_created} folder(s)", 0)

    def _count_items_recursive(self, path: str):
        """Count all files and directories recursively."""
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            yield item_path
            if os.path.isdir(item_path):
                yield from self._count_items_recursive(item_path)

    def _copy_dir_contents_to_image(
        self,
        disk,
        source_dir: str,
        dest_path: list[str],
        progress: ProgressDialog,
        current_item: list[int],
        errors: list[str]
    ):
        """Recursively copy directory contents to disk image."""
        try:
            items = os.listdir(source_dir)
        except OSError as e:
            errors.append(f"{source_dir}: {e}")
            return

        for item_name in items:
            item_path = os.path.join(source_dir, item_name)

            # Update progress
            if not progress.update(current_item[0], f"Copying {item_name}..."):
                return  # Cancelled

            # Convert to DOS 8.3 name
            try:
                name, ext = validate_filename(item_name.upper())
                dos_name = name.rstrip() + ('.' + ext.rstrip() if ext.rstrip() else '')
            except Exception:
                if os.path.isdir(item_path):
                    dos_name = item_name.upper()[:8]
                else:
                    dos_name = item_name.upper()[:12]

            item_dest = dest_path + [dos_name]

            if os.path.isdir(item_path):
                # Create directory and recurse
                try:
                    disk.create_directory(item_dest)
                except V9KError as e:
                    if "exists" not in str(e).lower():
                        errors.append(f"{dos_name}: {e}")
                        continue

                self._copy_dir_contents_to_image(
                    disk, item_path, item_dest, progress, current_item, errors
                )
            else:
                # Copy file
                try:
                    with open(item_path, 'rb') as f:
                        data = f.read()
                    disk.write_file(item_dest, data)
                    current_item[0] += 1
                except V9KError as e:
                    errors.append(f"{dos_name}: {e}")
                except OSError as e:
                    errors.append(f"{item_name}: {e}")

    def _on_delete(self, event):
        """Delete selected files and directories."""
        if self._readonly:
            wx.MessageBox(
                "Disk image is read-only",
                "Cannot Delete",
                wx.OK | wx.ICON_WARNING,
                self
            )
            return

        selected = self._file_panel.file_list.get_selected_entries()
        if not selected:
            return

        # Filter out parent entry
        items_to_delete = [
            (idx, entry) for idx, entry in selected
            if entry is not None
        ]

        if not items_to_delete:
            return

        # Separate files and directories
        files = [(idx, e) for idx, e in items_to_delete
                 if not (isinstance(e, DirectoryEntry) and e.is_directory)]
        dirs = [(idx, e) for idx, e in items_to_delete
                if isinstance(e, DirectoryEntry) and e.is_directory]

        # Confirm deletion (if enabled in preferences)
        if self._prefs.get('confirm_delete', True):
            names = [entry.full_name + ('\\' if isinstance(entry, DirectoryEntry) and entry.is_directory else '')
                     for _, entry in items_to_delete]
            if len(names) == 1:
                item_type = "folder" if dirs else "file"
                msg = f"Delete {item_type} '{names[0]}'?"
                if dirs:
                    msg += "\n\nThis will delete the folder and all its contents."
            else:
                file_count = len(files)
                dir_count = len(dirs)
                parts = []
                if file_count > 0:
                    parts.append(f"{file_count} file(s)")
                if dir_count > 0:
                    parts.append(f"{dir_count} folder(s)")
                msg = f"Delete {' and '.join(parts)}?\n\n" + "\n".join(names[:10])
                if len(names) > 10:
                    msg += f"\n... and {len(names) - 10} more"
                if dirs:
                    msg += "\n\nFolders will be deleted with all their contents."

            result = wx.MessageBox(
                msg,
                "Confirm Delete",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )

            if result != wx.YES:
                return

        # Delete items
        disk = self._get_current_disk()
        errors = []
        deleted_files = 0
        deleted_dirs = 0

        # Delete files first
        for idx, entry in files:
            try:
                path = list(self._current_path)
                path.append(entry.full_name)
                disk.delete_file(path)
                deleted_files += 1
            except V9KError as e:
                errors.append(f"{entry.full_name}: {e}")

        # Delete directories (recursively)
        for idx, entry in dirs:
            try:
                path = list(self._current_path)
                path.append(entry.full_name)
                disk.delete_directory(path, recursive=True)
                deleted_dirs += 1
            except V9KError as e:
                errors.append(f"{entry.full_name}\\: {e}")

        # Refresh listing
        self._refresh_file_list()

        # Mark as dirty if anything was deleted
        if deleted_files > 0 or deleted_dirs > 0:
            self._mark_dirty()

        # Show result
        total = deleted_files + deleted_dirs
        if errors:
            parts = []
            if deleted_files > 0:
                parts.append(f"{deleted_files} file(s)")
            if deleted_dirs > 0:
                parts.append(f"{deleted_dirs} folder(s)")
            msg = f"Deleted {', '.join(parts) if parts else '0 items'} with {len(errors)} error(s):\n\n"
            msg += "\n".join(errors)
            wx.MessageBox(msg, "Delete Complete", wx.OK | wx.ICON_WARNING, self)
        else:
            parts = []
            if deleted_files > 0:
                parts.append(f"{deleted_files} file(s)")
            if deleted_dirs > 0:
                parts.append(f"{deleted_dirs} folder(s)")
            self._statusbar.SetStatusText(f"Deleted {', '.join(parts)}", 0)

    def _on_properties(self, event):
        """Show properties for selected file."""
        selected = self._file_panel.file_list.get_selected_entries()
        if not selected:
            return

        # Show properties for first selected file
        idx, entry = selected[0]
        if entry is None:
            return

        path = self._build_path_display()
        if self._current_path:
            path += "\\" + entry.full_name
        else:
            path = os.path.basename(self._image_path) + ":\\" + entry.full_name

        dlg = PropertiesDialog(self, entry, path)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_about(self, event):
        """Show about dialog."""
        dlg = AboutDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_preferences(self, event):
        """Show preferences dialog."""
        dlg = PreferencesDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            # Update recent menu in case max count changed
            self._update_recent_menu()
        dlg.Destroy()

    # Drag and drop callbacks
    def _export_files_for_drag(self, internal_paths: list[str]) -> list[str]:
        """
        Export files and directories to temporary location for drag operation.

        Args:
            internal_paths: List of internal paths (e.g., ['SUBDIR\\FILE.COM'])

        Returns:
            List of temporary file/directory paths
        """
        if not self._disk:
            return []

        disk = self._get_current_disk()
        temp_dir = create_temp_export_dir()
        temp_paths = []

        for internal_path in internal_paths:
            try:
                # Parse path
                parts = internal_path.split('\\')
                name = parts[-1] if parts else internal_path

                # Check if it's a directory or file using find_entry
                try:
                    entry = disk.find_entry(parts)
                    if entry and entry.is_directory:
                        # Export directory recursively
                        dir_temp_path = os.path.join(temp_dir, name)
                        self._export_dir_for_drag(disk, parts, dir_temp_path)
                        temp_paths.append(dir_temp_path)
                        continue
                except Exception:
                    pass

                # Read file
                data = disk.read_file(parts)

                # Write to temp
                temp_path = os.path.join(temp_dir, name)
                with open(temp_path, 'wb') as f:
                    f.write(data)
                temp_paths.append(temp_path)

            except Exception:
                continue  # Skip files that can't be exported

        return temp_paths

    def _export_dir_for_drag(self, disk, source_path: list[str], dest_dir: str):
        """Recursively export a directory from the disk image for drag operation."""
        os.makedirs(dest_dir, exist_ok=True)

        try:
            entries = disk.list_files(source_path)
        except Exception:
            return

        for entry in entries:
            if entry.is_dot_entry or entry.is_volume_label:
                continue

            entry_source = source_path + [entry.full_name]
            entry_dest = os.path.join(dest_dir, entry.full_name)

            if entry.is_directory:
                self._export_dir_for_drag(disk, entry_source, entry_dest)
            else:
                try:
                    data = disk.read_file(entry_source)
                    with open(entry_dest, 'wb') as f:
                        f.write(data)
                except Exception:
                    continue

    def _is_disk_image_file(self, path: str) -> bool:
        """
        Check if a file path appears to be a disk image.

        Args:
            path: File path to check

        Returns:
            True if the file has a recognized disk image extension
        """
        ext = os.path.splitext(path)[1].lower()
        return ext in ('.img', '.ima', '.dsk')

    def _import_dropped_files_at_pos(self, local_paths: list[str], x: int, y: int) -> bool:
        """
        Import dropped files, checking if drop was on a folder.

        Args:
            local_paths: List of local file paths
            x: X coordinate of drop
            y: Y coordinate of drop

        Returns:
            True if operation was successful
        """
        # Check if drop is on a folder
        target_folder = None
        file_list = self._file_panel.file_list

        # HitTest to find item at drop position
        item_idx, flags = file_list.HitTest((x, y))

        if item_idx >= 0:
            entry = file_list.get_entry_at(item_idx)
            if entry is not None and isinstance(entry, DirectoryEntry) and entry.is_directory:
                # Dropped onto a folder - use it as target
                target_folder = entry.full_name

        return self._import_dropped_files(local_paths, target_folder)

    def _import_dropped_files(self, local_paths: list[str], target_folder: str | None = None) -> bool:
        """
        Import dropped files into the disk image, or open a dropped disk image.

        Args:
            local_paths: List of local file paths
            target_folder: Optional folder name to import into (if dropped on a folder)

        Returns:
            True if operation was successful
        """
        if not local_paths:
            return False

        # Check if exactly one disk image file was dropped
        disk_images = [p for p in local_paths if self._is_disk_image_file(p)]

        if len(disk_images) == 1 and len(local_paths) == 1:
            # A single disk image was dropped
            dropped_image = disk_images[0]

            if not os.path.exists(dropped_image):
                wx.MessageBox(
                    f"File not found: {dropped_image}",
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                    self
                )
                return False

            if self._disk is None:
                # No image open - defer opening so drag icon clears first
                wx.CallAfter(self._open_image, dropped_image)
                return True
            else:
                # An image is already open - defer the dialog so drag icon clears
                wx.CallAfter(self._handle_dropped_image_with_open, dropped_image, local_paths)
                return True

        # Not a single disk image - treat as files/folders to copy into current image
        if not self._disk or self._readonly:
            if not self._disk:
                wx.MessageBox(
                    "No disk image is open.\n\n"
                    "Open a disk image first, or drop a disk image file to open it.",
                    "No Image Open",
                    wx.OK | wx.ICON_INFORMATION,
                    self
                )
            else:
                wx.MessageBox(
                    "Cannot insert files: disk image is read-only",
                    "Read-Only",
                    wx.OK | wx.ICON_WARNING,
                    self
                )
            return False

        # Determine target path (current directory or target folder)
        target_path = list(self._current_path)
        if target_folder:
            target_path.append(target_folder)

        # Separate files and directories
        files = [p for p in local_paths if os.path.isfile(p)]
        dirs = [p for p in local_paths if os.path.isdir(p)]

        # Copy files first
        if files:
            self._copy_files_to_image(files, target_path)

        # Then copy directories
        for dir_path in dirs:
            self._copy_dir_to_image(dir_path, target_path)

        return True

    def _handle_dropped_image_with_open(self, dropped_image: str, local_paths: list[str]):
        """Handle a dropped disk image when another image is already open."""
        dlg = wx.MessageDialog(
            self,
            f"A disk image is already open.\n\n"
            f"Would you like to:\n"
            f"• Open '{os.path.basename(dropped_image)}' (closes current image)\n"
            f"• Insert it as a file into the current image",
            "Open or Insert?",
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
        )
        dlg.SetYesNoLabels("Open", "Insert")

        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            # Open it (closes current image)
            self._open_image(dropped_image)
        elif result == wx.ID_NO:
            # Insert as file into current image
            if self._readonly:
                wx.MessageBox(
                    "Cannot insert file: disk image is read-only",
                    "Read-Only",
                    wx.OK | wx.ICON_WARNING,
                    self
                )
                return
            self._copy_files_to_image(local_paths)
        # else: Cancel - do nothing

    def open_file(self, path: str, partition_idx: int | None = None):
        """
        Open a disk image file (public API for command-line argument).

        Args:
            path: Path to the disk image file
            partition_idx: Optional partition index to open directly (for hard disks)
        """
        self._open_image(path, partition_idx=partition_idx)
