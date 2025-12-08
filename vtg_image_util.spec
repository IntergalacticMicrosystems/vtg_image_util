# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Victor 9000 Disk Image Utility
# Builds both CLI and GUI executables

block_cipher = None

# CLI Executable Analysis
cli_a = Analysis(
    ['cli_main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'vtg_image_util',
        'vtg_image_util.__main__',
        'vtg_image_util.commands',
        'vtg_image_util.constants',
        'vtg_image_util.cpm',
        'vtg_image_util.creator',
        'vtg_image_util.exceptions',
        'vtg_image_util.fat12',
        'vtg_image_util.floppy',
        'vtg_image_util.formatter',
        'vtg_image_util.harddisk',
        'vtg_image_util.info',
        'vtg_image_util.logging_config',
        'vtg_image_util.models',
        'vtg_image_util.utils',
        'vtg_image_util.verify',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['wx', 'wxPython'],
    noarchive=False,
    optimize=0,
)

cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)

cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    cli_a.binaries,
    cli_a.datas,
    [],
    name='vtg_image_util',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# GUI Executable Analysis
gui_a = Analysis(
    ['gui_main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'vtg_image_util',
        'vtg_image_util.__main__',
        'vtg_image_util.commands',
        'vtg_image_util.constants',
        'vtg_image_util.cpm',
        'vtg_image_util.creator',
        'vtg_image_util.exceptions',
        'vtg_image_util.fat12',
        'vtg_image_util.floppy',
        'vtg_image_util.formatter',
        'vtg_image_util.harddisk',
        'vtg_image_util.info',
        'vtg_image_util.logging_config',
        'vtg_image_util.models',
        'vtg_image_util.utils',
        'vtg_image_util.verify',
        'vtg_image_util.gui',
        'vtg_image_util.gui.__main__',
        'vtg_image_util.gui.dialogs',
        'vtg_image_util.gui.drag_drop',
        'vtg_image_util.gui.file_list',
        'vtg_image_util.gui.icons',
        'vtg_image_util.gui.main',
        'vtg_image_util.gui.main_frame',
        'vtg_image_util.gui.preferences',
        'vtg_image_util.gui.preferences_dialog',
        'vtg_image_util.gui.toolbar',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.datas,
    [],
    name='vtg_image_util_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
