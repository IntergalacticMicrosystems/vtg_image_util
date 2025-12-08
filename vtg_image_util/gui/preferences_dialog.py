"""
Preferences dialog for the disk image utility GUI.

Allows users to configure application settings.
"""

import wx

from .preferences import get_preferences


class PreferencesDialog(wx.Dialog):
    """Dialog for editing application preferences."""

    def __init__(self, parent):
        super().__init__(
            parent,
            title="Preferences",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self._prefs = get_preferences()
        self._create_controls()
        self._layout_controls()
        self._load_values()

        self.SetMinSize((400, 300))
        self.Fit()
        self.Centre()

    def _create_controls(self):
        """Create all dialog controls."""
        # Recent files settings
        self._recent_label = wx.StaticText(self, label="Maximum recent files:")
        self._recent_spin = wx.SpinCtrl(self, min=1, max=20, initial=10)

        # Confirmation settings
        self._confirm_delete = wx.CheckBox(self, label="Confirm before deleting files")
        self._confirm_overwrite = wx.CheckBox(self, label="Confirm before overwriting files")

        # Buttons
        self._btn_ok = wx.Button(self, wx.ID_OK, "OK")
        self._btn_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
        self._btn_reset = wx.Button(self, label="Reset to Defaults")

        # Bind events
        self._btn_ok.Bind(wx.EVT_BUTTON, self._on_ok)
        self._btn_reset.Bind(wx.EVT_BUTTON, self._on_reset)

    def _layout_controls(self):
        """Layout the controls."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Recent files section
        recent_box = wx.StaticBox(self, label="Recent Files")
        recent_sizer = wx.StaticBoxSizer(recent_box, wx.HORIZONTAL)
        recent_sizer.Add(self._recent_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        recent_sizer.Add(self._recent_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(recent_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Confirmations section
        confirm_box = wx.StaticBox(self, label="Confirmations")
        confirm_sizer = wx.StaticBoxSizer(confirm_box, wx.VERTICAL)
        confirm_sizer.Add(self._confirm_delete, 0, wx.ALL, 5)
        confirm_sizer.Add(self._confirm_overwrite, 0, wx.ALL, 5)
        main_sizer.Add(confirm_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Add spacer
        main_sizer.AddStretchSpacer()

        # Button sizer
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self._btn_reset, 0, wx.RIGHT, 10)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._btn_ok, 0, wx.RIGHT, 5)
        btn_sizer.Add(self._btn_cancel, 0)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(main_sizer)

    def _load_values(self):
        """Load current preference values into controls."""
        self._recent_spin.SetValue(self._prefs.get('max_recent_files', 10))
        self._confirm_delete.SetValue(self._prefs.get('confirm_delete', True))
        self._confirm_overwrite.SetValue(self._prefs.get('confirm_overwrite', True))

    def _save_values(self):
        """Save control values to preferences."""
        self._prefs.set('max_recent_files', self._recent_spin.GetValue())
        self._prefs.set('confirm_delete', self._confirm_delete.GetValue())
        self._prefs.set('confirm_overwrite', self._confirm_overwrite.GetValue())

    def _on_ok(self, event):
        """Handle OK button."""
        self._save_values()
        self.EndModal(wx.ID_OK)

    def _on_reset(self, event):
        """Handle Reset to Defaults button."""
        self._recent_spin.SetValue(10)
        self._confirm_delete.SetValue(True)
        self._confirm_overwrite.SetValue(True)
