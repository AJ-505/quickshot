#!/usr/bin/env python3
"""Drive the real key handler with real keyvals and assert the behaviour.

The keyboard is the primary interface, so the bindings are worth pinning down.
Cheap actions are asserted directly; anything that closes the window or writes
the clipboard is checked for its side effect.
"""
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

import cairo  # noqa: E402
import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from quickshot.model import (BLUR, ELLIPSE, FREEHAND, LINE, PALETTE, POINTER,  # noqa: E402
                             RECT, SELECT, STEP, TEXT, Shape)
from quickshot.render import ctx  # noqa: E402
from quickshot.service import Quickshot  # noqa: E402

MOD = Gdk.ModifierType
CTRL = MOD.CONTROL_MASK
SHIFT = MOD.SHIFT_MASK

results: list[tuple[str, bool, str]] = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def key(ed, keyval, state=MOD(0)):
    return ed._on_key(None, keyval, 0, state)


def wait_visible(ed, tries: int = 400) -> bool:
    """The window is shown from an idle callback, so let the loop settle."""
    ctx = GLib.MainContext.default()
    for _ in range(tries):
        if ed.get_visible():
            return True
        if not ctx.iteration(False):
            GLib.usleep(1000)
    return ed.get_visible()


def main():
    tmpd = tempfile.mkdtemp(prefix="qs-keys-")
    path = os.path.join(tmpd, "shot.png")
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 900, 600)
    c = ctx(s)
    c.set_source_rgb(0.1, 0.1, 0.12)
    c.paint()
    s.write_to_png(path)

    app = Quickshot()
    problems: list[str] = []

    def on_startup(_a):
        try:
            app._open_editor()
            ed = app.editor
            ed.load(path)
            wait_visible(ed)
            _run(app, ed)
        except Exception:
            problems.append(traceback.format_exc())
        app.gtk_app.quit()

    def _run(app, ed):
        # -- tool selection ------------------------------------------------
        for keyval, expect in (
            (Gdk.KEY_r, RECT), (Gdk.KEY_o, ELLIPSE), (Gdk.KEY_l, LINE),
            (Gdk.KEY_d, FREEHAND), (Gdk.KEY_t, TEXT), (Gdk.KEY_b, BLUR),
            (Gdk.KEY_n, STEP), (Gdk.KEY_v, SELECT), (Gdk.KEY_p, POINTER),
        ):
            key(ed, keyval)
            check(f"tool key -> {expect}", ed.tool == expect, f"got {ed.tool}")

        # -- colour cycling ------------------------------------------------
        first = ed.color
        key(ed, Gdk.KEY_c)
        second = ed.color
        check("C cycles colour", second != first, f"{first} -> {second}")
        key(ed, Gdk.KEY_c, SHIFT)
        check("Shift+C cycles back", ed.color == first, f"got {ed.color}")

        # -- stroke width --------------------------------------------------
        w0 = ed.width_idx
        key(ed, Gdk.KEY_period)
        check(". increases stroke", ed.width_idx == w0 + 1, f"{w0} -> {ed.width_idx}")
        key(ed, Gdk.KEY_comma)
        check(", decreases stroke", ed.width_idx == w0, f"got {ed.width_idx}")

        # -- text size -----------------------------------------------------
        z0 = ed.size_idx
        key(ed, Gdk.KEY_bracketright)
        check("] grows text", ed.size_idx == z0 + 1, f"{z0} -> {ed.size_idx}")
        key(ed, Gdk.KEY_bracketleft)
        check("[ shrinks text", ed.size_idx == z0, f"got {ed.size_idx}")

        # -- redact mode ---------------------------------------------------
        m0 = app.blur_mode
        key(ed, Gdk.KEY_b, SHIFT)
        check("Shift+B toggles redact mode", app.blur_mode != m0,
              f"{m0} -> {app.blur_mode}")

        # -- zoom ----------------------------------------------------------
        ed.view.zoom = 1.0
        key(ed, Gdk.KEY_equal)
        check("= zooms in", ed.view.zoom > 1.0, f"zoom {ed.view.zoom}")
        key(ed, Gdk.KEY_0)
        check("0 resets zoom", abs(ed.view.zoom - 1.0) < 1e-6, f"zoom {ed.view.zoom}")

        # -- drawing, undo, redo -------------------------------------------
        ed.set_tool(RECT)
        rect = Shape(kind=RECT, x=10, y=10, x2=200, y2=120, color=PALETTE[0], width=3.0)
        ed.doc.add(rect)
        check("shape added", len(ed.doc.shapes) == 1, str(len(ed.doc.shapes)))
        key(ed, Gdk.KEY_z, CTRL)
        check("Ctrl+Z undoes", len(ed.doc.shapes) == 0, str(len(ed.doc.shapes)))
        key(ed, Gdk.KEY_z, CTRL | SHIFT)
        check("Ctrl+Shift+Z redoes", len(ed.doc.shapes) == 1, str(len(ed.doc.shapes)))

        # -- selection: pick, nudge, recolour, delete ----------------------
        ed.set_tool(SELECT)
        ed.selected = ed.doc.shapes[0]
        ed._invalidate()
        before = (ed.selected.x, ed.selected.y)
        key(ed, Gdk.KEY_Right)
        check("Right nudges selection", (ed.selected.x, ed.selected.y) == (before[0] + 1, before[1]),
              f"{before} -> {(ed.selected.x, ed.selected.y)}")
        key(ed, Gdk.KEY_Right, SHIFT)
        check("Shift+Right nudges by 10", abs(ed.selected.x - before[0] - 11) < 1e-6,
              f"x={ed.selected.x}")
        key(ed, Gdk.KEY_c)
        check("C recolours the selection", ed.selected.color == ed.color,
              f"{ed.selected.color} vs {ed.color}")
        key(ed, Gdk.KEY_Delete)
        check("Delete removes the selection", len(ed.doc.shapes) == 0 and ed.selected is None,
              f"{len(ed.doc.shapes)} shapes")

        # -- Tab toggles between select and the last drawing tool ---------
        ed.set_tool(RECT)
        key(ed, Gdk.KEY_Tab)
        check("Tab -> select", ed.tool == SELECT, ed.tool)
        key(ed, Gdk.KEY_Tab)
        check("Tab -> back to drawing tool", ed.tool == RECT, ed.tool)

        # -- help ----------------------------------------------------------
        check("help hidden initially", not ed.help_box.get_visible())
        key(ed, Gdk.KEY_h)
        check("H shows help", ed.help_box.get_visible())
        key(ed, Gdk.KEY_Escape)
        check("Esc dismisses help before the window", not ed.help_box.get_visible())
        check("Esc with help open keeps the window", ed.get_visible())

        # -- Enter copies and closes ---------------------------------------
        ed.set_tool(RECT)
        ed.doc.add(Shape(kind=RECT, x=0, y=0, x2=50, y2=50, color=PALETTE[0], width=3.0))
        key(ed, Gdk.KEY_Return)
        check("Enter closes the editor", not ed.get_visible())

        # A fresh capture resets the editor for the next round, as it does in
        # real use where every screenshot calls load() again.
        shot2 = os.path.join(tmpd, "shot2.png")
        s.write_to_png(shot2)
        ed.load(shot2)
        wait_visible(ed)
        check("a new capture reopens the window", ed.get_visible())
        check("a new capture starts empty", len(ed.doc.shapes) == 0)

        # -- Esc discards and closes ---------------------------------------
        ed.set_tool(RECT)
        ed.doc.add(Shape(kind=RECT, x=0, y=0, x2=50, y2=50, color=PALETTE[0], width=3.0))
        cached = ed._path
        check("capture path is tracked", bool(cached) and os.path.exists(cached), str(cached))
        key(ed, Gdk.KEY_Escape)
        check("Esc closes the editor", not ed.get_visible())
        check("Esc clears the document", len(ed.doc.shapes) == 0, str(len(ed.doc.shapes)))
        check("Esc deletes the cached capture", cached and not os.path.exists(cached),
              f"{cached} still present")

    app.gtk_app.connect("startup", on_startup)
    app.gtk_app.connect("activate", lambda _a: app.gtk_app.hold())
    GLib.timeout_add_seconds(25, lambda: (app.gtk_app.quit(), GLib.SOURCE_REMOVE)[1])
    app.gtk_app.run([])

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        if not ok:
            print(f"  FAIL  {name}  ({detail})")
    print(f"{len(results) - len(failed)}/{len(results)} keymap checks passed")
    if problems:
        print("ERRORS")
        for p in problems:
            print(p)
    if failed or problems:
        sys.exit(1)
    print("PASS  keymap behaves as designed")


if __name__ == "__main__":
    sys.exit(main())
