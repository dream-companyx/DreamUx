"""Автообновление DreamUX. /update [check|now|core|gui|force]"""

import os
import json
import urllib.request

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
VERSION_FILE = os.path.join(KERNEL_DIR, "version.json")


CORE_BASE = "https://raw.githubusercontent.com/dream-companyx/DreamUx/main"
GUI_BASE = "https://raw.githubusercontent.com/dream-companyx/dreamux_gui/main"

CORE_FILES = {
    "kernel.py":                f"{CORE_BASE}/kernel.py",
    "plugins/__init__.py":      f"{CORE_BASE}/plugins/__init__.py",
    "plugins/base.py":          f"{CORE_BASE}/plugins/base.py",
    "plugins/core.py":          f"{CORE_BASE}/plugins/core.py",
    "plugins/filesystem.py":    f"{CORE_BASE}/plugins/filesystem.py",
    "plugins
