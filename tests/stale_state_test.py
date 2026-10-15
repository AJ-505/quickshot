#!/usr/bin/env python3
"""The editor lifecycle invariants that keep the hotkey working.

Closing leaves the editor hidden and empty. A new trigger after a close shows
a fresh capture. A trigger while an image is open raises the editor and never
starts a second capture. A window that is visible but holds nothing recovers
on the next trigger instead of swallowing it.
"""
import os

import gi  # noqa: E402
import support  # noqa: F401, E402 (must come first)

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from quickshot.service import Quickshot  # noqa: E402

problems: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        problems.append(name)


def pump():
    ctx = GLib.MainContext.default()
    while ctx.iteration(False):
        pass


def arm():
    os.environ["QUICKSHOT_TEST_IMAGE"] = support.make_png("s.png", 640, 400)


def main() -> int:
    ran = []
    arm()
    app = Quickshot()

    def run():
        ran.append(True)
        ed = app.editor
        check("starts hidden", not ed.get_visible())
        check("starts empty", ed.img is None)

        app.trigger()
        pump()
        check("trigger shows the editor", ed.get_visible())
        check("trigger loads the image", ed.img is not None)

        first = ed.img
        app.trigger()
        pump()
        check("second trigger keeps the same image", ed.img is first)
        check("second trigger keeps the editor visible", ed.get_visible())

        del os.environ["QUICKSHOT_TEST_IMAGE"]
        app.trigger()
        pump()
        check("trigger with an image open starts no capture", app.capture is None)
        check("trigger with an image open keeps the image", ed.img is first)
        arm()

        ed._close()
        pump()
        check("close hides the window", not ed.get_visible())
        check("close clears the image", ed.img is None)
        check("close clears the document", len(ed.doc.shapes) == 0)
        check("close drops the capture", app.capture is None)

        arm()
        app.trigger()
        pump()
        check("trigger after close shows the editor", ed.get_visible())
        check("trigger after close loads a new image", ed.img is not None)

        ed._close()
        pump()
        arm()
        ed.set_visible(True)
        check("stale window is visible", ed.get_visible())
        check("stale window holds no image", ed.img is None)
        app.trigger()
        pump()
        check("trigger recovers a stale window", ed.get_visible() and ed.img is not None)

        ed.reset()
        check("reset hides the window", not ed.get_visible())
        check("reset clears the image", ed.img is None)
        check("reset clears the document", len(ed.doc.shapes) == 0)

        app.gtk_app.quit()

    def on_startup(_a):
        app._open_editor()
        GLib.timeout_add(50, run)

    app.gtk_app.connect("startup", on_startup)
    app.gtk_app.connect("activate", lambda _a: app.gtk_app.hold())
    GLib.timeout_add_seconds(25, lambda: (app.gtk_app.quit(), GLib.SOURCE_REMOVE)[1])
    app.gtk_app.run([])

    if not ran:
        problems.append("scenario never ran")
    if problems:
        print(f"\nFAIL  {len(problems)} check(s) failed")
        return 1
    print("\nPASS  editor lifecycle holds: close, retrigger, second trigger, stale recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
