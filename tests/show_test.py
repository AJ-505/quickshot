#!/usr/bin/env python3
"""load() presents the editor at once, never after a deferred retry loop.

Regression test for the bug where the editor appeared about 100 s after the
capture because the show waited for an allocation a hidden window never gets.
After load() returns the window must be visible, must stay visible on the next
main-loop iteration, and must map within a tight wall-clock bound.
"""
import time

import gi  # noqa: E402
import support  # noqa: F401, E402 (must come first)

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from quickshot.service import Quickshot  # noqa: E402

MAP_BOUND_S = 1.5
problems: list[str] = []
ran: list[bool] = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        problems.append(name)


def main() -> int:
    app = Quickshot()
    shot = support.make_png("s.png", 1280, 800)

    def run():
        ran.append(True)
        ed = app.editor
        mapped = {}
        ed.connect("map", lambda *_: mapped.setdefault("t", time.monotonic()))

        t0 = time.monotonic()
        ed.load(shot)
        load_ms = (time.monotonic() - t0) * 1000
        check("visible when load returns", ed.get_visible())
        check("image is loaded", ed.img is not None)

        GLib.MainContext.default().iteration(False)
        check("visible on the next main-loop iteration", ed.get_visible())

        deadline = t0 + MAP_BOUND_S
        ctx = GLib.MainContext.default()
        while "t" not in mapped and time.monotonic() < deadline:
            ctx.iteration(False)
            time.sleep(0.005)
        map_ms = (mapped["t"] - t0) * 1000 if "t" in mapped else None
        check(f"mapped within {MAP_BOUND_S} s", map_ms is not None,
              f"load {load_ms:.0f} ms, map {map_ms:.0f} ms" if map_ms is not None
              else f"load {load_ms:.0f} ms, never mapped")
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
    print("\nPASS  load() shows the editor immediately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
