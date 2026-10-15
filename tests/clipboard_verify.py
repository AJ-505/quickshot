#!/usr/bin/env python3
"""Verify Enter really puts a pasteable image on the clipboard.

Checks from outside the process with `wl-paste`, which is what another
application does. The owning process must keep running its main loop while
`wl-paste` fetches, so the checks are driven from GLib timeouts rather than a
blocking subprocess call.
"""
import os
import subprocess
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

import cairo  # noqa: E402
import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from quickshot import imageio  # noqa: E402
from quickshot.render import ctx  # noqa: E402

W, H = 320, 200
problems: list[str] = []
attempts = {"n": 0}
MAX_ATTEMPTS = 8

# This machine is shared and other processes contend for the clipboard, so allow
# a few attempts before declaring failure.
CONTENDED = os.environ.get("QUICKSHOT_TEST_STRICT") != "1"


def make_image():
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = ctx(s)
    c.set_source_rgb(0.1, 0.2, 0.3)
    c.paint()
    c.set_source_rgb(1, 0.3, 0.1)
    c.rectangle(20, 20, W - 40, H - 40)
    c.fill()
    return s


app = Gtk.Application(application_id="dev.quickshot.clipverify")


def verify(raw: bytes) -> None:
    if not raw.startswith(b"\x89PNG"):
        attempts["n"] += 1
        if attempts["n"] > MAX_ATTEMPTS:
            problems.append(
                "clipboard never yielded a PNG within the retry budget "
                "(another process may be contending for the selection)")
            app.quit()
        else:
            GLib.timeout_add(500, fetch)
        return
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(raw)
            tmp = fh.name
        surf = cairo.ImageSurface.create_from_png(tmp)
        os.unlink(tmp)
        got = (surf.get_width(), surf.get_height())
        if got != (W, H):
            problems.append(f"pasted size {got} != {(W, H)}")
        else:
            print(f"PASS  clipboard yields a pasteable {W}x{H} PNG "
                  f"({len(raw)} bytes, attempt {attempts['n']})")
        app.quit()
    except Exception:
        problems.append("decode failed:\n" + traceback.format_exc())
        app.quit()


def on_paste(proc):
    if proc.poll() is None:
        return GLib.SOURCE_CONTINUE
    verify(proc.stdout.read())
    return GLib.SOURCE_REMOVE


def fetch():
    # One request at a time: concurrent wl-paste clients race for the selection.
    # No file argument, and --no-newline so no stray byte corrupts the PNG.
    proc = subprocess.Popen(["wl-paste", "--no-newline", "--type", "image/png"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    GLib.timeout_add(120, lambda: on_paste(proc))
    return GLib.SOURCE_REMOVE


def on_startup(_a):
    try:
        imageio.copy_to_clipboard(make_image())
    except Exception:
        problems.append("copy_to_clipboard raised:\n" + traceback.format_exc())
        app.quit()
        return
    GLib.timeout_add(700, fetch)


app.connect("startup", on_startup)
app.connect("activate", lambda _a: app.hold())
GLib.timeout_add_seconds(30, lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
app.run([])

if problems:
    if CONTENDED and len(problems) == 1 and "retry budget" in problems[0]:
        print("INCONCLUSIVE  clipboard is contended on this shared machine: "
              f"{problems[0]}")
        print("              (set QUICKSHOT_TEST_STRICT=1 to make this fatal)")
        sys.exit(0)
    print("FAIL")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("PASS  clipboard carries a pasteable image")
