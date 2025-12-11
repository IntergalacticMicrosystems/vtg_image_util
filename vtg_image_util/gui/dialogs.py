"""
Custom dialogs for the GUI.

Includes progress dialog, properties dialog, partition selector, and about dialog.
"""

import wx

from ..models import DirectoryEntry, VirtualVolumeLabel
from ..cpm import CPMFileInfo


class ProgressDialog(wx.ProgressDialog):
    """
    Progress dialog for multi-file operations.

    Wraps wx.ProgressDialog with additional functionality.
    """

    def __init__(
        self,
        title: str,
        message: str,
        maximum: int,
        parent: wx.Window
    ):
        super().__init__(
            title,
            message,
            maximum=maximum,
            parent=parent,
            style=wx.PD_AUTO_HIDE | wx.PD_APP_MODAL | wx.PD_CAN_ABORT |
                  wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME
        )
        self._cancelled = False

    def update(self, value: int, message: str = "") -> bool:
        """
        Update the progress.

        Args:
            value: Current progress value
            message: Optional message to display

        Returns:
            True if operation should continue, False if cancelled
        """
        if message:
            result = self.Update(value, message)
        else:
            result = self.Update(value)

        # Result is a tuple (continue, skip) on newer wx versions
        if isinstance(result, tuple):
            self._cancelled = not result[0]
        else:
            self._cancelled = not result

        return not self._cancelled

    @property
    def cancelled(self) -> bool:
        """Check if operation was cancelled."""
        return self._cancelled


class PropertiesDialog(wx.Dialog):
    """Dialog showing file or directory properties."""

    def __init__(
        self,
        parent: wx.Window,
        entry: DirectoryEntry | CPMFileInfo,
        path: str
    ):
        super().__init__(
            parent,
            title="Properties",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self._create_ui(entry, path)
        self.SetMinSize((300, 200))
        self.Fit()
        self.Centre()

    def _create_ui(self, entry: DirectoryEntry | CPMFileInfo, path: str):
        """Create the dialog UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Create a grid for properties
        grid = wx.FlexGridSizer(cols=2, vgap=5, hgap=10)
        grid.AddGrowableCol(1)

        # Name
        grid.Add(wx.StaticText(self, label="Name:"))
        grid.Add(wx.StaticText(self, label=entry.full_name))

        # Path
        grid.Add(wx.StaticText(self, label="Path:"))
        grid.Add(wx.StaticText(self, label=path))

        # Size
        if isinstance(entry, DirectoryEntry) and entry.is_directory:
            size_text = "<Directory>"
        else:
            size = entry.file_size
            if size < 1024:
                size_text = f"{size:,} bytes"
            elif size < 1024 * 1024:
                size_text = f"{size:,} bytes ({size / 1024:.1f} KB)"
            else:
                size_text = f"{size:,} bytes ({size / (1024 * 1024):.1f} MB)"
        grid.Add(wx.StaticText(self, label="Size:"))
        grid.Add(wx.StaticText(self, label=size_text))

        # Attributes
        grid.Add(wx.StaticText(self, label="Attributes:"))
        attr_text = self._format_attributes(entry)
        grid.Add(wx.StaticText(self, label=attr_text))

        # Date/time (FAT only)
        if isinstance(entry, DirectoryEntry):
            if entry.modify_date != 0:
                date = entry.modify_date
                time = entry.modify_time
                year = ((date >> 9) & 0x7F) + 1980
                month = (date >> 5) & 0x0F
                day = date & 0x1F
                hour = (time >> 11) & 0x1F
                minute = (time >> 5) & 0x3F
                second = (time & 0x1F) * 2
                date_text = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
            else:
                date_text = "Not set"
            grid.Add(wx.StaticText(self, label="Modified:"))
            grid.Add(wx.StaticText(self, label=date_text))

            # First cluster
            grid.Add(wx.StaticText(self, label="First cluster:"))
            grid.Add(wx.StaticText(self, label=str(entry.first_cluster)))

        # CP/M specific
        if isinstance(entry, CPMFileInfo):
            grid.Add(wx.StaticText(self, label="User:"))
            grid.Add(wx.StaticText(self, label=str(entry.user)))

            grid.Add(wx.StaticText(self, label="Extents:"))
            grid.Add(wx.StaticText(self, label=str(len(entry.extents))))

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 10)

        # OK button
        btn_sizer = self.CreateButtonSizer(wx.OK)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(sizer)

    def _format_attributes(self, entry: DirectoryEntry | CPMFileInfo) -> str:
        """Format attributes as human-readable string."""
        attrs = []
        if isinstance(entry, DirectoryEntry):
            if entry.attributes & 0x01:
                attrs.append("Read-Only")
            if entry.attributes & 0x02:
                attrs.append("Hidden")
            if entry.attributes & 0x04:
                attrs.append("System")
            if entry.attributes & 0x08:
                attrs.append("Volume Label")
            if entry.attributes & 0x10:
                attrs.append("Directory")
            if entry.attributes & 0x20:
                attrs.append("Archive")
        elif isinstance(entry, CPMFileInfo):
            if entry.is_read_only:
                attrs.append("Read-Only")
            if entry.is_system:
                attrs.append("System")

        return ", ".join(attrs) if attrs else "None"


class PartitionSelectDialog(wx.Dialog):
    """Dialog for selecting a partition on a hard disk."""

    def __init__(
        self,
        parent: wx.Window,
        partitions: list[dict]
    ):
        """
        Initialize the dialog.

        Args:
            parent: Parent window
            partitions: List of partition info dicts with keys:
                        index, name, capacity, capacity_bytes, cluster_size
        """
        super().__init__(
            parent,
            title="Select Partition",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self._partitions = partitions
        self._selected_index = 0 if partitions else -1

        self._create_ui()
        self.SetMinSize((400, 250))
        self.Fit()
        self.Centre()

    def _create_ui(self):
        """Create the dialog UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Label
        label = wx.StaticText(self, label="Select a partition to open:")
        sizer.Add(label, 0, wx.ALL, 10)

        # Partition list
        self._list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN
        )
        self._list.InsertColumn(0, "#", width=40)
        self._list.InsertColumn(1, "Name", width=150)
        self._list.InsertColumn(2, "Size", width=100)
        self._list.InsertColumn(3, "Cluster Size", width=80)

        for p in self._partitions:
            row = self._list.GetItemCount()
            self._list.InsertItem(row, str(p['index']))
            self._list.SetItem(row, 1, p['name'])
            size_mb = p['capacity_bytes'] / (1024 * 1024)
            self._list.SetItem(row, 2, f"{size_mb:.1f} MB")
            # Show cluster size instead of count
            cluster_kb = p['cluster_size'] / 1024
            self._list.SetItem(row, 3, f"{cluster_kb:.0f} KB")

        # Select first item
        if self._list.GetItemCount() > 0:
            self._list.Select(0)

        sizer.Add(self._list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(sizer)

        # Bind events
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)

    def _on_activate(self, event):
        """Handle double-click on partition."""
        self.EndModal(wx.ID_OK)

    def get_selected_partition(self) -> int:
        """Get the selected partition index."""
        sel = self._list.GetFirstSelected()
        if sel >= 0 and sel < len(self._partitions):
            return self._partitions[sel]['index']
        return -1


class AboutDialog(wx.Dialog):
    """About dialog showing application information."""

    def __init__(self, parent: wx.Window):
        super().__init__(
            parent,
            title="About Vtg Disk Image Utility",
            style=wx.DEFAULT_DIALOG_STYLE
        )

        self._create_ui()
        self.Fit()
        self.Centre()

    def _create_ui(self):
        """Create the dialog UI."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(self, label="Vtg Disk Image Utility")
        title_font = title.GetFont()
        title_font.SetPointSize(14)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Version
        version = wx.StaticText(self, label="Version 1.0.0")
        sizer.Add(version, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        # Description
        desc = wx.StaticText(
            self,
            label="A cross-platform utility for reading and writing\n"
                  "Victor 9000 and IBM PC floppy and hard disk images.",
            style=wx.ALIGN_CENTER
        )
        sizer.Add(desc, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, 20)

        # Supported formats
        formats = wx.StaticText(
            self,
            label="\nSupported formats:\n"
                  "- Victor 9000 FAT12 floppy disks\n"
                  "- Victor 9000 hard disks (multiple partitions)\n"
                  "- Victor 9000 CP/M-86 floppy disks\n"
                  "- IBM PC FAT12 floppy disks",
            style=wx.ALIGN_CENTER
        )
        sizer.Add(formats, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # OK button
        btn_sizer = self.CreateButtonSizer(wx.OK)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(sizer)
