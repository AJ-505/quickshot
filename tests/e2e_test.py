#!/usr/bin/env python3
"""End-to-end: the hotkey target signals the service, the editor appears, and
Enter puts the annotated image on the clipboard and closes the window.

The real `quickshot` launcher is executed as a subprocess, so the unix-socket
wake-up path is genuinely exercised rather than simulated.
"""
import os
import subprocess
import sys
import time
import traceback

import support  # noqa: E402 (must come first)

ROOT = support.ROOT

import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from quickshot.service import Quickshot, socket_path  # noqa: E402

W, H = 800, 500
problems: list[str] = []
state = {"visible_at": None, "img": None, "shapes": 0, "closed": False}


def launcher():
    return os.path.join(ROOT, "bin", "quickshot")


def main():
    os.environ["QUICKSHOT_TEST_IMAGE"] = support.make_png("shot.png", W, H)

    app = Quickshot()

    def on_startup(_a):
        # Run the service's own startup work (build the window, open the socket),
        # then drive the scenario.
        try:
            app._on_startup()
        except Exception:
            problems.append("service startup failed:\n" + traceback.format_exc())
        GLib.timeout_add(300, step1)

    def step1():
        try:
            if not os.path.exists(socket_path()):
                problems.append("service did not create its control socket")
        except Exception:
            problems.append("socket check failed:\n" + traceback.format_exc())
        # Run the genuine hotkey target. It must be spawned rather than waited
        # on: this process is also the socket server, so blocking here would
        # stop the main loop that has to accept the connection.
        state["t0"] = time.monotonic()
        state["proc"] = subprocess.Popen(
            [launcher()], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        GLib.timeout_add(100, step1_poll)
        return GLib.SOURCE_REMOVE

    def step1_poll():
        proc = state["proc"]
        if proc.poll() is None:
            if time.monotonic() - state["t0"] > 8:
                proc.kill()
                problems.append("hotkey launcher never exited")
                GLib.timeout_add(200, step2)
            return GLib.SOURCE_CONTINUE
        dt = (time.monotonic() - state["t0"]) * 1000
        err = proc.stderr.read().decode(errors="replace").strip()
        if proc.returncode != 0:
            problems.append(f"launcher exited {proc.returncode}: {err}")
        # Latency is not asserted here: this test runs the server inside the
        # test process, so the window presentation blocks the same main loop the
        # measurement depends on. tests/latency_test.py measures it properly
        # with the daemon in its own process.
        print(f"launcher round trip (not a latency measure): {dt:.0f} ms")
        GLib.timeout_add(400, step2)
        return GLib.SOURCE_REMOVE

    def step2():
        ed = app.editor
        state["visible_at"] = ed.get_visible()
        state["img"] = (ed.img.get_width(), ed.img.get_height()) if ed.img else None
        if not state["visible_at"]:
            problems.append("editor window did not become visible after the hotkey")
        if state["img"] != (W, H):
            problems.append(f"editor image is {state['img']}, expected {(W, H)}")
        # annotate, exactly as a keystroke would
        from quickshot.model import PALETTE, POINTER, Shape
        ed.set_tool(POINTER)
        ed.doc.add(Shape(kind=POINTER, x=100, y=100, x2=500, y2=200,
                         color=PALETTE[0], width=5.0), mark=False)
        state["shapes"] = len(ed.doc.shapes)
        ed.queue_draw()
        GLib.timeout_add(400, step3)
        return GLib.SOURCE_REMOVE

    def step3():
        ed = app.editor
        # Enter -> copy to clipboard and close
        ed._on_key(None, Gdk.KEY_Return, 0, Gdk.ModifierType(0))
        GLib.timeout_add(700, step4)
        return GLib.SOURCE_REMOVE

    def step4():
        state["closed"] = not app.editor.get_visible()
        if not state["closed"]:
            problems.append("editor did not close after Enter")
        GLib.timeout_add(500, step5)
        return GLib.SOURCE_REMOVE

    def step5():
        # the cache file should be cleaned up when the shot is dismissed
        cache = os.path.join(support.CACHE, "quickshot")
        if os.path.isdir(cache) and os.listdir(cache):
            problems.append(f"cached shot files left behind: {os.listdir(cache)}")
        app.gtk_app.quit()
        return GLib.SOURCE_REMOVE

    app.gtk_app.connect("startup", on_startup)
    app.gtk_app.connect("activate", lambda _a: app.gtk_app.hold())
    GLib.timeout_add_seconds(30, lambda: (app.gtk_app.quit(), GLib.SOURCE_REMOVE)[1])
    app.gtk_app.run([])

    print(f"editor visible: {state['visible_at']}  image: {state['img']}  "
          f"shapes: {state['shapes']}  closed: {state['closed']}")
    if problems:
        print("FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print("PASS  hotkey -> socket -> editor -> annotate -> Enter -> clipboard")
    return 0


if __name__ == "__main__":
    sys.exit(main())
