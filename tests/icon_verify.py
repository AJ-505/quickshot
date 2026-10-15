#!/usr/bin/env python3
"""Every icon must parse and load.

A malformed SVG only fails at runtime, deep inside a toolbar callback, which is
an unpleasant place to discover it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib  # noqa: E402

from quickshot import icons  # noqa: E402

fails = []
for name in sorted(icons.ICONS):
    try:
        Gdk.Texture.new_from_bytes(GLib.Bytes.new(icons.ICONS[name].encode("utf-8")))
    except Exception as exc:
        fails.append(f"{name}: {exc}")

if fails:
    print("FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"PASS  {len(icons.ICONS)} icons parse and load")
