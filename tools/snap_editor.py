#!/usr/bin/env python3
"""Render the real editor window to a PNG, without touching the user's screen.

Usage: tools/snap_editor.py IMAGE.png OUT.png [scenario]

Scenarios: plain, annotated, help, text.

The window is mapped (GNOME denies it focus, so it opens behind other windows)
and then rendered through its own GSK renderer, so the PNG is what the user
would see, including CSS and overlays.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import GLib, Graphene, Gtk  # noqa: E402

from quickshot.model import BLUR, CURSOR, ELLIPSE, LINE, PALETTE, POINTER, RECT, STEP, TEXT, Shape  # noqa: E402
from quickshot.service import Quickshot  # noqa: E402


def annotate(ed) -> None:
    w, h = ed.img.get_width(), ed.img.get_height()
    shapes = [
        Shape(kind=POINTER, x=w * 0.15, y=h * 0.2, x2=w * 0.42, y2=h * 0.45, color=PALETTE[0]),
        Shape(kind=RECT, x=w * 0.5, y=h * 0.15, x2=w * 0.85, y2=h * 0.4, color=PALETTE[1]),
        Shape(kind=ELLIPSE, x=w * 0.1, y=h * 0.6, x2=w * 0.3, y2=h * 0.85, color=PALETTE[2]),
        Shape(kind=BLUR, x=w * 0.55, y=h * 0.6, x2=w * 0.8, y2=h * 0.8, color=PALETTE[0]),
        Shape(kind=STEP, x=w * 0.45, y=h * 0.7, x2=w * 0.45, y2=h * 0.7, color=PALETTE[0], size=26, step=1),
        Shape(kind=TEXT, x=w * 0.5, y=h * 0.45, x2=w * 0.5, y2=h * 0.45, color=PALETTE[0], size=26, text="Look here"),
    ]
    for s in shapes:
        ed.doc.add(s)
    ed._invalidate()


def selected(ed) -> None:
    annotate(ed)
    ed.selected = ed.doc.shapes[1]
    ed._invalidate()


def redact(ed) -> None:
    w, h = ed.img.get_width(), ed.img.get_height()
    ed.doc.add(Shape(kind=BLUR, x=w * 0.2, y=h * 0.3, x2=w * 0.6, y2=h * 0.6, block=12))
    ed.doc.add(Shape(kind=CURSOR, x=w * 0.7, y=h * 0.3, x2=w * 0.7, y2=h * 0.3, size=20))
    ed.doc.add(Shape(kind=LINE, x=w * 0.1, y=h * 0.8, x2=w * 0.5, y2=h * 0.85, color=PALETTE[3]))
    ed._invalidate()


SCENARIOS = {
    "selected": selected,
    "redact": redact,
    "plain": lambda ed: None,
    "annotated": annotate,
    "help": lambda ed: ed.toggle_help(),
    "text": lambda ed: (ed.set_tool(TEXT), ed._begin_text(ed.img.get_width() * 0.3, ed.img.get_height() * 0.3)),
    "typed": lambda ed: (ed.set_tool(TEXT), ed._begin_text(ed.img.get_width() * 0.3, ed.img.get_height() * 0.3),
                         ed.entry.set_text("Fix this button")),
}


def snapshot_png(win: Gtk.Window, out: str) -> bool:
    w, h = win.get_width(), win.get_height()
    if w < 2 or h < 2:
        return False
    paintable = Gtk.WidgetPaintable.new(win)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    if node is None:
        return False
    texture = win.get_renderer().render_texture(node, Graphene.Rect().init(0, 0, w, h))
    texture.save_to_png(out)
    return True


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    src, out = sys.argv[1], os.path.abspath(sys.argv[2])
    scenario = SCENARIOS[sys.argv[3] if len(sys.argv) > 3 else "plain"]
    work = os.path.join(tempfile.mkdtemp(prefix="qs-snap-"), "shot.png")
    shutil.copyfile(src, work)
    app = Quickshot()
    result = {"ok": False}

    def finish() -> bool:
        result["ok"] = snapshot_png(app.editor, out)
        app.editor._close()
        app.gtk_app.quit()
        return GLib.SOURCE_REMOVE

    def on_startup(*_a) -> None:
        app._open_editor()
        app.editor.load(work)
        scenario(app.editor)
        app.gtk_app.hold()
        GLib.timeout_add(900, finish)

    app.on_editor_closed = lambda: None
    app.gtk_app.connect("startup", on_startup)
    app.gtk_app.connect("activate", lambda *_a: None)
    app.gtk_app.run([])
    print(("wrote " + out) if result["ok"] else "snapshot failed")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
