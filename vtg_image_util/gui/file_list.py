"""
File list control for displaying directory contents.

Uses wx.ListCtrl in virtual mode for efficient display of directory entries.
"""

import wx
import wx.lib.mixins.listctrl as listmix

from ..models import DirectoryEntry
from ..cpm import CPMFileInfo
from ..utils import match_filename
from .icons import get_icon_manager


class FileListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
    """
    Virtual list control for displaying directory entries.

    Supports both FAT12 DirectoryEntry and CP/M CPMFileInfo entries.
    """

    # Column indices
    COL_NAME = 0
    COL_SIZE = 1
    COL_DATE = 2
    COL_ATTR = 3

    def __init__(self, parent):
        wx.ListCtrl.__init__(
            self, parent,
            style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_EDIT_LABELS | wx.BORDER_SUNKEN
        )
        listmix.ListCtrlAutoWidthMixin.__init__(self)

        self._all_entries: list[DirectoryEntry | CPMFileInfo] = []  # All entries
        self._entries: list[DirectoryEntry | CPMFileInfo] = []  # Filtered entries
        self._show_parent_entry = False
        self._sort_column = 0
        self._sort_ascending = True
        self._is_cpm = False
        self._filter_text = ""

        # Set up columns
        self.InsertColumn(self.COL_NAME, "Name", width=200)
        self.InsertColumn(self.COL_SIZE, "Size", width=100, format=wx.LIST_FORMAT_RIGHT)
        self.InsertColumn(self.COL_DATE, "Date", width=120)
        self.InsertColumn(self.COL_ATTR, "Attr", width=60)

        # Set up image list
        icon_mgr = get_icon_manager()
        self.AssignImageList(icon_mgr.get_small_image_list(), wx.IMAGE_LIST_SMALL)

        # Bind events
        self.Bind(wx.EVT_LIST_COL_CLICK, self._on_column_click)

    def set_entries(
        self,
        entries: list[DirectoryEntry | CPMFileInfo],
        show_parent: bool = False,
        is_cpm: bool = False
    ):
        """
        Set the directory entries to display.

        Args:
            entries: List of DirectoryEntry or CPMFileInfo objects
            show_parent: Whether to show a ".." parent entry at the top
            is_cpm: Whether this is a CP/M disk (affects display)
        """
        self._all_entries = list(entries)
        self._show_parent_entry = show_parent
        self._is_cpm = is_cpm
        self._apply_filter()
        self._sort_entries()
        self.SetItemCount(self._get_display_count())
        self.Refresh()

    def clear(self):
        """Clear all entries."""
        self._all_entries = []
        self._entries = []
        self._show_parent_entry = False
        self._filter_text = ""
        self.SetItemCount(0)
        self.Refresh()

    def set_filter(self, filter_text: str):
        """
        Set the filter text for filtering entries.

        Args:
            filter_text: Text to filter by (supports wildcards * and ?)
        """
        self._filter_text = filter_text.strip()
        self._apply_filter()
        self._sort_entries()
        self.SetItemCount(self._get_display_count())
        self.Refresh()

    def get_filter(self) -> str:
        """Get the current filter text."""
        return self._filter_text

    def _apply_filter(self):
        """Apply the current filter to entries."""
        if not self._filter_text:
            self._entries = list(self._all_entries)
            return

        # Check if filter looks like a wildcard pattern
        filter_text = self._filter_text.upper()
        has_wildcard = '*' in filter_text or '?' in filter_text

        if has_wildcard:
            # Use wildcard matching
            self._entries = [
                entry for entry in self._all_entries
                if match_filename(filter_text, self._get_name(entry))
            ]
        else:
            # Simple substring match
            self._entries = [
                entry for entry in self._all_entries
                if filter_text in self._get_name(entry).upper()
            ]

    def get_selected_entries(self) -> list[tuple[int, DirectoryEntry | CPMFileInfo | None]]:
        """
        Get the selected entries.

        Returns:
            List of (index, entry) tuples. For parent entry, entry is None.
        """
        selected = []
        item = self.GetFirstSelected()
        while item != -1:
            entry = self._get_entry_at(item)
            selected.append((item, entry))
            item = self.GetNextSelected(item)
        return selected

    def get_entry_at(self, index: int) -> DirectoryEntry | CPMFileInfo | None:
        """Get the entry at the given display index."""
        return self._get_entry_at(index)

    def _get_display_count(self) -> int:
        """Get total number of items to display."""
        count = len(self._entries)
        if self._show_parent_entry:
            count += 1
        return count

    def _get_entry_at(self, index: int) -> DirectoryEntry | CPMFileInfo | None:
        """Get entry at display index, accounting for parent entry."""
        if self._show_parent_entry:
            if index == 0:
                return None  # Parent entry
            index -= 1
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def _sort_entries(self):
        """Sort entries by current sort column."""
        if not self._entries:
            return

        # Separate directories and files
        dirs = []
        files = []

        for entry in self._entries:
            if isinstance(entry, DirectoryEntry) and entry.is_directory:
                dirs.append(entry)
            else:
                files.append(entry)

        # Sort function based on column
        def get_sort_key(entry):
            if self._sort_column == self.COL_NAME:
                return self._get_name(entry).lower()
            elif self._sort_column == self.COL_SIZE:
                return self._get_size(entry)
            elif self._sort_column == self.COL_DATE:
                return self._get_date_sort_key(entry)
            elif self._sort_column == self.COL_ATTR:
                return self._get_attr(entry)
            return ""

        # Sort directories and files separately
        dirs.sort(key=get_sort_key, reverse=not self._sort_ascending)
        files.sort(key=get_sort_key, reverse=not self._sort_ascending)

        # Directories first, then files
        self._entries = dirs + files

    def _on_column_click(self, event):
        """Handle column header click for sorting."""
        col = event.GetColumn()
        if col == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = col
            self._sort_ascending = True
        self._sort_entries()
        self.Refresh()

    # Virtual list control methods
    def OnGetItemText(self, item: int, column: int) -> str:
        """Get the text for a cell."""
        if self._show_parent_entry and item == 0:
            # Parent directory entry
            if column == self.COL_NAME:
                return ".."
            elif column == self.COL_SIZE:
                return "<DIR>"
            return ""

        entry = self._get_entry_at(item)
        if entry is None:
            return ""

        if column == self.COL_NAME:
            return self._get_name(entry)
        elif column == self.COL_SIZE:
            return self._get_size_display(entry)
        elif column == self.COL_DATE:
            return self._get_date_display(entry)
        elif column == self.COL_ATTR:
            return self._get_attr(entry)
        return ""

    def OnGetItemImage(self, item: int) -> int:
        """Get the image index for an item."""
        icon_mgr = get_icon_manager()

        if self._show_parent_entry and item == 0:
            return icon_mgr.IDX_PARENT

        entry = self._get_entry_at(item)
        if entry is None:
            return icon_mgr.IDX_FILE

        if isinstance(entry, DirectoryEntry) and entry.is_directory:
            return icon_mgr.IDX_FOLDER
        return icon_mgr.IDX_FILE

    def OnGetItemAttr(self, item: int) -> wx.ItemAttr | None:
        """Get the attributes for an item (can be used for custom colors)."""
        return None

    # Helper methods for getting display values
    def _get_name(self, entry: DirectoryEntry | CPMFileInfo) -> str:
        """Get the display name for an entry."""
        if isinstance(entry, CPMFileInfo):
            return entry.full_name
        return entry.full_name

    def _get_size(self, entry: DirectoryEntry | CPMFileInfo) -> int:
        """Get the size for sorting."""
        if isinstance(entry, DirectoryEntry) and entry.is_directory:
            return -1  # Directories sort before files
        return entry.file_size

    def _get_size_display(self, entry: DirectoryEntry | CPMFileInfo) -> str:
        """Get the formatted size display."""
        if isinstance(entry, DirectoryEntry) and entry.is_directory:
            return "<DIR>"
        size = entry.file_size
        if size < 1024:
            return f"{size:,}"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def _get_date_sort_key(self, entry: DirectoryEntry | CPMFileInfo) -> int:
        """Get a sortable date key."""
        if isinstance(entry, DirectoryEntry):
            # Combine date and time into single sortable integer
            return (entry.modify_date << 16) | entry.modify_time
        return 0  # CP/M doesn't have dates

    def _get_date_display(self, entry: DirectoryEntry | CPMFileInfo) -> str:
        """Get the formatted date display."""
        if isinstance(entry, DirectoryEntry):
            # Decode FAT date/time format
            date = entry.modify_date
            time = entry.modify_time

            if date == 0:
                return ""

            # FAT date: bits 15-9 = year (0-127, 0=1980), 8-5 = month, 4-0 = day
            year = ((date >> 9) & 0x7F) + 1980
            month = (date >> 5) & 0x0F
            day = date & 0x1F

            # FAT time: bits 15-11 = hour, 10-5 = minute, 4-0 = second/2
            hour = (time >> 11) & 0x1F
            minute = (time >> 5) & 0x3F

            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
        return ""  # CP/M doesn't have dates

    def _get_attr(self, entry: DirectoryEntry | CPMFileInfo) -> str:
        """Get the attribute string."""
        if isinstance(entry, CPMFileInfo):
            # CP/M only has read-only and system attributes
            attrs = ""
            attrs += "R" if entry.is_read_only else "-"
            attrs += "S" if entry.is_system else "-"
            return attrs
        return entry.attr_string()


class FileListPanel(wx.Panel):
    """
    Panel containing the file list with address bar and search box.

    Provides a complete file browser interface.
    """

    def __init__(self, parent):
        super().__init__(parent)

        self._current_path = ""

        # Create controls
        self._path_text = wx.TextCtrl(
            self, style=wx.TE_READONLY,
            value="No disk image loaded"
        )

        # Search box
        self._search_box = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self._search_box.SetDescriptiveText("Filter files (supports * and ?)")
        self._search_box.ShowCancelButton(True)

        self._file_list = FileListCtrl(self)

        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Top bar with path and search
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_label = wx.StaticText(self, label="Path:")
        path_sizer.Add(path_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        path_sizer.Add(self._path_text, 1, wx.EXPAND)

        top_sizer.Add(path_sizer, 1, wx.EXPAND | wx.RIGHT, 10)
        top_sizer.Add(self._search_box, 0, wx.ALIGN_CENTER_VERTICAL, 0)

        sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self._file_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.SetSizer(sizer)

        # Bind events
        self._search_box.Bind(wx.EVT_TEXT, self._on_filter_changed)
        self._search_box.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_filter_clear)

    @property
    def file_list(self) -> FileListCtrl:
        """Get the file list control."""
        return self._file_list

    def set_path(self, path: str):
        """Set the displayed path."""
        self._current_path = path
        self._path_text.SetValue(path)
        # Clear filter when changing directories
        self._search_box.SetValue("")

    def get_path(self) -> str:
        """Get the current path."""
        return self._current_path

    def clear_filter(self):
        """Clear the search filter."""
        self._search_box.SetValue("")
        self._file_list.set_filter("")

    def _on_filter_changed(self, event):
        """Handle filter text change."""
        filter_text = self._search_box.GetValue()
        self._file_list.set_filter(filter_text)

    def _on_filter_clear(self, event):
        """Handle filter clear button click."""
        self._search_box.SetValue("")
        self._file_list.set_filter("")
