#!/usr/bin/env python3
"""Smoke test: build the real window, load a real image, draw a few frames.

Runs the actual GTK application on the current display for a couple of seconds
and reports any GLib log error, then exits. Catches the class of failure that a
static import check cannot: bad CSS, missing icons, a draw callback that throws.
"""
import os
import sys
import tempfile
import traceback

import cairo  # noqa: E402
import gi  # noqa: E402
import support  # noqa: F401, E402 (must come first)

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from quickshot.model import PALETTE, POINTER, RECT, STEP, Shape  # noqa: E402
from quickshot.render import ctx  # noqa: E402
from quickshot.service import Quickshot  # noqa: E402

problems: list[str] = []


def make_fixture(path: str) -> None:
    W, H = 1600, 900
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = ctx(s)
    c.set_source_rgb(0.13, 0.14, 0.17)
    c.paint()
    c.set_source_rgb(0.2, 0.22, 0.27)
    c.rectangle(0, 0, W, 56)
    c.fill()
    c.set_source_rgb(0.85, 0.86, 0.9)
    c.select_font_face("Monospace", 0, 0)
    c.set_font_size(20)
    for i in range(12):
        c.move_to(40, 110 + i * 34)
        c.show_text(f"  line {i:02d}  --  some sample terminal output here")
    c.set_source_rgb(0.95, 0.55, 0.25)
    c.rectangle(900, 400, 600, 70)
    c.fill()
    s.write_to_png(path)


def main() -> int:
    tmp = os.path.join(tempfile.mkdtemp(prefix="qs-smoke-"), "shot.png")
    make_fixture(tmp)
    frames = {"n": 0}
    app = Quickshot()

    def _setup() -> None:
        app._open_editor()
        ed = app.editor
        ed.load(tmp)

        # exercise the draw path with content of several kinds
        ed.doc.add(Shape(kind=RECT, x=200, y=150, x2=900, y2=500,
                         color=PALETTE[3], width=5.0), mark=False)
        ed.doc.add(Shape(kind=POINTER, x=300, y=300, x2=800, y2=340,
                         color=PALETTE[0], width=6.0), mark=False)
        ed.doc.add(Shape(kind=STEP, x=350, y=600, x2=350, y2=600, step=1,
                         color=PALETTE[0], size=30.0), mark=False)
        ed._invalidate()

        if len(ed.toolbar.tool_buttons) < 9:
            problems.append(f"toolbar only built {len(ed.toolbar.tool_buttons)} buttons")

        for t in ("rect", "text", "blur", "select", "pointer"):
            ed.set_tool(t)
        ed.set_color(PALETTE[2])

        out = ed.composite()
        if out.get_width() != ed.img.get_width():
            problems.append("composite changed dimensions")
        from quickshot import imageio
        imageio.save_png(out, os.path.dirname(tmp), "smoke")
        imageio.copy_to_clipboard(out)

    def on_startup(_a) -> None:
        # the service normally does this in its own startup handler
        try:
            _setup()
        except Exception:
            problems.append("startup setup raised:\n" + traceback.format_exc())

    def tick() -> bool:
        frames["n"] += 1
        if app.editor:
            app.editor.queue_draw()
        if frames["n"] >= 30:
            Gtk.Application.get_default().quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    app.gtk_app.connect("startup", on_startup)
    GLib.timeout_add(16, tick)
    app.gtk_app.run([])

    print(f"frames drawn: {frames['n']}")
    if problems:
        print("FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print("PASS  window built, drew frames, composite/save/clipboard ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(2)
