"""Screenshot capture via the XDG desktop portal.

This is the seam that makes the whole tool feel native: we ask the portal for an
*interactive* screenshot, which on GNOME reuses the exact drag-to-select overlay
that PrintScreen shows. The user selects a region with the muscle memory they
already have; we only decide what happens to the result.

The portal writes into its own Screenshots folder, so we immediately move the
file into our cache. A shot the user then discards leaves nothing behind in
~/Pictures.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"

CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "quickshot"
)


def cache_dir() -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


class CaptureCancelled(Exception):
    """The user dismissed the selection overlay."""


class CaptureFailed(Exception):
    """The portal refused or errored."""


def _variant_to_py(v):
    return v.unpack() if hasattr(v, "unpack") else v


class Capture:
    """One-shot portal request. Construct with a GLib main loop running."""

    def __init__(self, on_done: Callable[[str], None] | None = None,
                 on_error: Callable[[Exception], None] | None = None) -> None:
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._on_done = on_done
        self._on_error = on_error
        self._sub = 0
        self._timeout = 0
        self._settled = False
        self.busy = False

    def _finish(self) -> None:
        if self._sub:
            self._bus.signal_unsubscribe(self._sub)
            self._sub = 0
        if self._timeout:
            GLib.source_remove(self._timeout)
            self._timeout = 0
        self.busy = False

    def _fail(self, exc: Exception) -> None:
        if self._settled:
            return
        self._settled = True
        self._finish()
        if self._on_error:
            self._on_error(exc)

    def _succeed(self, path: str) -> None:
        if self._settled:
            return
        self._settled = True
        self._finish()
        if self._on_done:
            self._on_done(path)

    def _on_response(self, _conn, _sender, _path, _iface, _signal, params, *_a) -> None:
        try:
            code, results = params.unpack()
        except Exception as exc:  # pragma: no cover - malformed signal
            self._fail(CaptureFailed(str(exc)))
            return
        if code != 0:
            self._fail(CaptureCancelled(f"portal responded {code}"))
            return
        uri = None
        for k, v in results.items():
            if k == "uri":
                uri = _variant_to_py(v)
        if not uri:
            self._fail(CaptureFailed("portal returned no uri"))
            return
        src = Gio.File.new_for_uri(uri)
        raw = src.get_path()
        if not raw or not src.query_exists(None):
            self._fail(CaptureFailed("portal file vanished"))
            return
        try:
            dest = os.path.join(cache_dir(), f"shot-{int(time.time() * 1000)}.png")
            # Move, not copy: a discarded shot must not litter ~/Pictures.
            os.replace(raw, dest)
        except OSError as exc:
            self._fail(CaptureFailed(str(exc)))
            return
        self._succeed(dest)

    def start(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._settled = False
        token = f"quickshot{os.getpid()}{int(time.time() * 1000) % 100000}"
        options = {
            "interactive": GLib.Variant.new_boolean(True),
            "handle_token": GLib.Variant.new_string(token),
            "modal": GLib.Variant.new_boolean(True),
        }
        try:
            reply = self._bus.call_sync(
                PORTAL_BUS, PORTAL_PATH, "org.freedesktop.portal.Screenshot", "Screenshot",
                GLib.Variant("(sa{sv})", ("", options)), GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE, 20000, None,
            )
        except GLib.Error as exc:
            self._fail(CaptureFailed(exc.message))
            return
        handle = reply.unpack()[0]
        self._sub = self._bus.signal_subscribe(
            PORTAL_BUS, "org.freedesktop.portal.Request", "Response", handle, None,
            Gio.DBusSignalFlags.NONE, self._on_response,
        )
        # The overlay is modal, so the user will always answer -- but do not
        # leave the daemon wedged if something goes wrong.
        self._timeout = GLib.timeout_add_seconds(300, self._on_timeout)

    def _on_timeout(self) -> bool:
        self._fail(CaptureFailed("timed out waiting for selection"))
        return GLib.SOURCE_REMOVE
