#!/usr/bin/env python3
"""A stale editor must not swallow captures, and no window may be shown.

Regression test for the bug where a window flagged visible while holding no
image made `trigger()` a permanent no-op, so the hotkey did nothing.

`QUICKSHOT_SHUTTER_SETTLE_MS` is set absurdly high so the deferred show never
fires: this exercises the state machine without putting anything on screen.
"""
import os
import sys
import tempfile

os.environ["QUICKSHOT_SHUTTER_SETTLE_MS"] = "600000"

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

import cairo  # noqa: E402
import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from quickshot.render import ctx  # noqa: E402
from quickshot.service import Quickshot  # noqa: E402

problems: list[str] = []


def main() -> int:
    tmpd = tempfile.mkdtemp(prefix="qs-stale-")
    shot = os.path.join(tmpd, "s.png")
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 400)
    c = ctx(s)
    c.set_source_rgb(0.2, 0.4, 0.7)
    c.paint()
    s.write_to_png(shot)
    os.environ["QUICKSHOT_TEST_IMAGE"] = shot

    app = Quickshot()

    def check(name, cond, detail=""):
        print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
        if not cond:
            problems.append(name)

    def run():
        ed = app.editor
        # 1. simulate the stuck state: visible, but holding nothing
        ed.set_visible(True)
        check("stale window is visible", ed.get_visible())
        check("stale window holds no image", ed.img is None)

        # 2. a trigger must recover rather than bail
        app.trigger()
        check("trigger reset the stale window", not ed.get_visible(),
              f"visible={ed.get_visible()}")
        check("trigger loaded a new capture", ed.img is not None,
              f"img={ed.img}")

        # 3. a second trigger, with a real image present, must not clobber it
        first = ed.img
        ed.set_visible(True)
        app.trigger()
        check("existing editor is raised, not replaced", ed.img is first)
        check("existing editor stayed visible", ed.get_visible())

        # 4. reset() must leave a clean, hidden, empty editor
        ed.reset()
        check("reset hides the window", not ed.get_visible())
        check("reset clears the image", ed.img is None)
        check("reset clears the document", len(ed.doc.shapes) == 0)

        # 5. and a trigger after a reset still works
        app.trigger()
        check("trigger works after reset", ed.img is not None)

        # 6. a queued show must not resurrect a closed editor
        ed.load(shot)
        ed._close()
        pending = ed._show_source
        GLib.MainContext.default().iteration(False)
        check("close cancels the queued show", ed._show_source == 0,
              f"was {pending}")

        app.gtk_app.quit()

    def on_startup(_a):
        app._open_editor()
        GLib.timeout_add(50, run)

    app.gtk_app.connect("startup", on_startup)
    app.gtk_app.connect("activate", lambda _a: app.gtk_app.hold())
    GLib.timeout_add_seconds(25, lambda: (app.gtk_app.quit(), GLib.SOURCE_REMOVE)[1])
    app.gtk_app.run([])

    if problems:
        print(f"\nFAIL  {len(problems)} check(s) failed")
        return 1
    print("\nPASS  stale editor recovers; no capture is silently dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
