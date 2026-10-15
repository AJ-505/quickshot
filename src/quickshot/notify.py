"""Desktop notifications, used only for out-of-band events (save, errors)."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.freedesktop.Notifications"


def notify(summary: str = "Quickshot", body: str = "", urgency: str = "normal") -> None:
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.call_sync(
        BUS, "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "Notify",
        GLib.Variant("(susssasa{sv}i)",
                     ("quickshot", 0, "quickshot-symbolic", summary, body,
                      [], {"urgency": GLib.Variant.new_string(urgency)}, -1)),
        None, Gio.DBusCallFlags.NONE, 4000, None,
    )
