"""The resident service.

Lives as a systemd user service, starts at login, and never shows a window
until the hotkey fires. The hotkey target is a tiny launcher that writes a byte
to a unix socket, so waking the editor costs a socket round trip rather than a
Python start-up.
"""
from __future__ import annotations

import os
import socket
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .capture import Capture, CaptureCancelled
from .editor import Editor


def socket_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(base, f"quickshot-{os.getuid()}.sock")


def _socket_answers(path: str) -> bool:
    """True if a live instance is already listening on `path`."""
    if not os.path.exists(path):
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(path)
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


class Quickshot:
    def __init__(self) -> None:
        self.gtk_app = Gtk.Application(
            application_id="dev.quickshot.Quickshot",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.blur_mode = "mosaic"
        self.editor: Editor | None = None
        self.capture: Capture | None = None
        self._sock: socket.socket | None = None
        self._chan = None
        self._watch = 0

    # -- lifecycle -------------------------------------------------------
    def _open_editor(self) -> None:
        """Pre-create the editor so showing it later is just a present().

        Must run from the GApplication `startup` handler: GTK rejects windows
        constructed before that signal.
        """
        if self.editor is not None:
            return
        w = Editor(self)
        w.connect("close-request", self._on_close_request)
        self.editor = w
        w.hide()

    def _on_close_request(self, *_a) -> bool:
        if self.editor is not None and self.editor._entry_pending is not None:
            self.editor._cancel_entry()
            return True
        return False  # allow hide; the window is undeletable anyway

    def start(self) -> None:
        self.gtk_app.connect("startup", self._on_startup)
        self.gtk_app.connect("activate", lambda *_: self._open_editor())
        self.gtk_app.run([])

    def _on_startup(self, *_a) -> None:
        self._open_editor()
        if not self._listen():
            sys.stderr.write("quickshot: another instance owns the socket; exiting\n")
            self.gtk_app.quit()

    def _listen(self) -> bool:
        """Bind the control socket. Returns False if another instance owns it.

        Without this, every time the socket went missing the hotkey launcher
        started another daemon, and they would each unlink and rebind the same
        path, leaving several processes fighting over one control socket.
        """
        path = socket_path()
        if _socket_answers(path):
            return False
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.bind(path)
            os.chmod(path, 0o600)
        except OSError as exc:
            sys.stderr.write(f"quickshot: cannot bind {path}: {exc}\n")
            return False
        s.listen(8)
        s.setblocking(False)
        self._sock = s
        # Gio.unix_fd_add is not introspected in this GLib, so watch the fd
        # through a GLib IOChannel instead. The channel must outlive the watch.
        self._chan = GLib.IOChannel.unix_new(s.fileno())
        self._chan.set_encoding(None)
        self._watch = GLib.io_add_watch(self._chan, GLib.IO_IN, self._on_accept)
        sys.stderr.write(f"quickshot: listening on {path} (pid {os.getpid()})\n")
        return True

    def _on_accept(self, _chan, _cond, *_a) -> bool:
        # Nothing raised in here may escape: this runs on the main loop, and a
        # daemon that dies takes the hotkey with it.
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return True
        try:
            conn.settimeout(0.5)
            data = conn.recv(64)
        except OSError:
            data = b""
        if data[:1] == b"s":
            # status probe: report state instead of starting a capture
            try:
                conn.sendall((self._status_line() + "\n").encode())
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
            return True
        try:
            conn.close()
        except OSError:
            pass
        try:
            self.trigger()
        except Exception as exc:
            self.notify_error(f"capture failed: {exc}")
        return True

    def _status_line(self) -> str:
        ed = self.editor
        if ed is None:
            return "editor=none"
        has = "yes" if ed.img is not None else "no"
        try:
            dims = f"{ed.img.get_width()}x{ed.img.get_height()}" if ed.img else "-"
        except Exception:
            dims = "?"
        return (f"pid={os.getpid()} visible={ed.get_visible()} has_image={has} "
                f"image={dims} size={ed.get_width()}x{ed.get_height()} "
                f"capturing={'yes' if (self.capture and self.capture.busy) else 'no'}")

    def _log(self, msg: str) -> None:
        """Visible in `journalctl --user -u quickshot.service`."""
        sys.stderr.write(f"quickshot: {msg}\n")
        sys.stderr.flush()

    # -- capture ---------------------------------------------------------
    def trigger(self) -> None:
        self._log("trigger received")
        ed = self.editor
        if ed is not None and ed.get_visible():
            if ed.img is not None:
                # A real editor is up: just raise it rather than starting a
                # second capture on top of it.
                self._log("editor already holds an image; raising it")
                ed.present()
                return
            # Visible but holding nothing: a stale window from an earlier
            # session. Reset it, otherwise it silently swallows every trigger.
            self._log("editor flagged visible but empty; resetting stale window")
            ed.reset()
        if self.capture is not None and self.capture.busy:
            self._log("capture already in flight; ignoring")
            return
        # Test seam: lets the end-to-end tests exercise the hotkey -> editor
        # path without a human dragging the portal's selection overlay.
        forced = os.environ.get("QUICKSHOT_TEST_IMAGE")
        if forced:
            self._on_captured(forced)
            return
        self.capture = Capture(
            on_done=self._on_captured,
            on_error=self._on_capture_error,
        )
        self._log("requesting the portal selection overlay")
        self.capture.start()

    def _on_captured(self, path: str) -> None:
        if self.editor is None:
            return
        answered = time.monotonic()
        try:
            self.editor.load(path)
        except Exception as exc:
            self.editor.discard_file(path)
            self.notify_error(f"could not open the capture: {exc}")
            return
        self._log(f"editor shown {(time.monotonic() - answered) * 1000:.0f} ms after the capture")

    def _on_capture_error(self, exc: Exception) -> None:
        if isinstance(exc, CaptureCancelled):
            return  # user pressed Escape: not an error, not worth a notification
        self.notify_error(str(exc))

    def on_editor_closed(self) -> None:
        self.capture = None

    # -- notifications ---------------------------------------------------
    def notify(self, body: str) -> None:
        try:
            from .notify import notify
            notify(body)
        except Exception:
            pass

    def notify_error(self, body: str) -> None:
        try:
            from .notify import notify
            notify(f"Quickshot: {body}", urgency="critical")
        except Exception:
            sys.stderr.write(f"quickshot: {body}\n")


def main() -> int:
    GLib.set_prgname("quickshot")
    GLib.set_application_name("Quickshot")
    app = Quickshot()
    app.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
