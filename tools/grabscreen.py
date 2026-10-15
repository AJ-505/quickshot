#!/usr/bin/env python3
"""Capture the whole screen with no selection UI, via the portal.

`interactive: false` makes the portal grab every monitor and return a URI
without showing the drag overlay, which is what makes automated visual checks
of the editor possible.
"""
import os
import sys
import time

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"


def main() -> int:
    dest = sys.argv[1] if len(sys.argv) > 1 else "screen.png"
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    done = {"ok": False}
    loop = GLib.MainLoop()
    token = f"probe{int(time.time())}"

    def on_response(*a):
        if not a[2].endswith("/" + token):
            return None
        params = a[5]
        code, results = params.unpack()
        uri = None
        for k, v in results.items():
            if k == "uri":
                uri = v.unpack() if hasattr(v, "unpack") else v
        if uri and code == 0:
            src = Gio.File.new_for_uri(uri)
            src.copy(Gio.File.new_for_path(os.path.abspath(dest)),
                     Gio.FileCopyFlags.OVERWRITE, None, None, None)
            done["ok"] = True
        loop.quit()
        return None

    bus.signal_subscribe(BUS, "org.freedesktop.portal.Request", "Response",
                         None, None, Gio.DBusSignalFlags.NONE, on_response)
    opts = {"interactive": GLib.Variant.new_boolean(False),
            "handle_token": GLib.Variant.new_string(token)}
    bus.call_sync(BUS, PATH, "org.freedesktop.portal.Screenshot", "Screenshot",
                  GLib.Variant("(sa{sv})", ("", opts)),
                  GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, 20000, None)
    GLib.timeout_add_seconds(25, loop.quit)
    loop.run()
    print(("wrote " + dest) if done["ok"] else "capture failed")
    return 0 if done["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
