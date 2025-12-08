#!/usr/bin/env python3
"""
Entry point script for CLI executable.
Used by PyInstaller to build the CLI version.
"""

import sys
from vtg_image_util.__main__ import main

if __name__ == '__main__':
    sys.exit(main())
