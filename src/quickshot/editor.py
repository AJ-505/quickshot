"""The editor: a full-screen, keyboard-first annotation surface.

Design notes that matter for the "seamless" goal:
  * The window is pre-created and hidden; showing it is a `present()`, not a
    construction, so the hotkey-to-editors latency is a frame, not a second.
  * No title bar, no decorations, no separate "save" dialog. The default exit is
    one keystroke (Enter -> clipboard) that also closes the window.
  * Every action has a single-key binding; the toolbar is only there to teach
    those bindings.
"""
from __future__ import annotations

import math
import os

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import imageio, render
from .model import (BLUR, ELLIPSE, FREEHAND, LINE, PALETTE, POINTER, RECT,
                    SELECT, STEP, TEXT, TOOLS, Doc, Shape)
from .render import View
from .toolbar import Toolbar, install_css

PAD = 18              # margin around the screenshot
TOOLBAR_SPACE = 74    # room for the floating toolbar below the image
MAX_SCREEN_SHARE = 0.86   # never fill the whole monitor
MIN_IMAGE_SCALE = 0.2
MAX_IMAGE_SCALE = 1.0
MIN_WINDOW_W = 640
MIN_WINDOW_H = 360
WIDTHS = [1.5, 2.5, 3.5, 5.0, 7.0, 10.0, 14.0]

SIZES = [12, 16, 20, 26, 32, 40, 52, 68]
CURSORS = {
    SELECT: "default", RECT: "crosshair", ELLIPSE: "crosshair",
    LINE: "crosshair", FREEHAND: "pencil", TEXT: "text",
    BLUR: "cell", STEP: "crosshair", POINTER: "crosshair",
}

HELP_ROWS = [
    ("Tools", [
        ("P", "pointer / arrow"), ("R", "rectangle"), ("O", "ellipse"),
        ("L", "line"), ("D", "freehand"), ("T", "text"),
        ("B", "redact"), ("N", "numbered step"), ("V", "select / move"),
    ]),
    ("Adjust", [
        ("C", "cycle colour"), (", / .", "stroke width"),
        ("[ / ]", "text size"), ("Shift+B", "mosaic <-> blur"),
        ("wheel", "zoom"), ("0", "reset zoom"), ("space+drag", "pan"),
    ]),
    ("Finish", [
        ("Enter", "copy + close"), ("Ctrl+S", "save + close"),
        ("Esc", "discard"), ("Ctrl+Z", "undo"), ("Ctrl+Shift+Z", "redo"),
        ("Del", "delete selection"), ("H", "this panel"),
    ]),
]


class Editor(Gtk.Window):
    def __init__(self, app) -> None:
        super().__init__(application=app.gtk_app, title="Quickshot")
        self.app = app
        self.doc = Doc()
        self.img: cairo.ImageSurface | None = None
        self.view = View(scale=1.0, fit=1.0, ox=0.0, oy=0.0, zoom=1.0)
        self.tool = POINTER
        self.color = PALETTE[0]
        self.width_idx = 2
        self.size_idx = 3
        self.selected: Shape | None = None
        self.last_draw_tool = POINTER

        self._preview: Shape | None = None
        self._drag: dict | None = None
        self._band = None
        self._last_xy: tuple[float, float] | None = None
        self._space_down = False
        self._shift_down = False
        self._entry_pending: Shape | None = None
        self._cache: cairo.ImageSurface | None = None
        self._cache_key = None
        self._closing = False
        self._last_pointer_motion = 0

        install_css()
        self.add_css_class("qs-window")
        self.set_decorated(False)
        self.set_deletable(False)
        self.set_resizable(False)
        self.set_modal(True)
        # Dialog-typed windows are not given the compositor's fullscreen/window
        # open animation, which is another source of a bright transitional frame.
        try:
            self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        except Exception:
            pass
        if hasattr(self, "set_skip_taskbar_hints"):
            self.set_skip_taskbar_hints(True)
        if hasattr(self, "set_skip_taskbar"):
            self.set_skip_taskbar(True)

        self.overlay = Gtk.Overlay()
        self.area = Gtk.DrawingArea()
        self.area.set_focusable(True)
        self.area.set_can_focus(True)
        self.area.add_css_class("quickshot-canvas")
        self.area.set_draw_func(self._on_draw)
        self.overlay.set_child(self.area)

        self.toolbar = Toolbar(self)
        self.overlay.add_overlay(self.toolbar)

        self.entry_frame = self._build_entry()
        self.overlay.add_overlay(self.entry_frame)

        self.help_box = self._build_help()
        self.help_box.set_visible(False)
        self.overlay.add_overlay(self.help_box)

        self.set_child(self.overlay)

        # Input. GtkEventControllerLegacy would be the obvious choice, but
        # PyGObject cannot marshal its GdkEvent parameter (it arrives as None),
        # so the canvas is driven by discrete gesture controllers instead.
        self._click = Gtk.GestureClick()
        self._click.set_button(1)
        self._click.connect("pressed", self._on_press)
        self._click.connect("released", self._on_release)
        self.area.add_controller(self._click)

        # Middle and right drag pan, on both press and release we only need the
        # bracket; the motion controller supplies the coordinates.
        for btn in (2, 3):
            g = Gtk.GestureClick()
            g.set_button(btn)
            g.connect("pressed", self._on_press)
            g.connect("released", self._on_release)
            self.area.add_controller(g)

        self._motion = Gtk.EventControllerMotion()
        self._motion.connect("motion", self._on_pointer_motion)
        self.area.add_controller(self._motion)

        self._scroll = Gtk.EventControllerScroll()
        self._scroll.set_flags(Gtk.EventControllerScrollFlags.DISCRETE)
        self._scroll.connect("scroll", self._on_scroll)
        self.area.add_controller(self._scroll)

        # A second motion controller on the window keeps the toolbar awake even
        # when the pointer is over the chrome rather than the canvas.
        self._hover = Gtk.EventControllerMotion()
        self._hover.connect("motion", self._on_motion)
        self.add_controller(self._hover)

        self._keys = Gtk.EventControllerKey()
        self._keys.connect("key-pressed", self._on_key)
        self._keys.connect("key-released", self._on_key_release)
        self.add_controller(self._keys)

    # ---------------------------------------------------------------- setup
    def load(self, path: str) -> None:
        self._path = path
        self._closing = False
        self.doc = Doc()
        self.img = imageio.load_png(path)
        self.selected = None
        self._preview = None
        self._drag = None
        self._cache = None
        self._cache_key = None
        self._band = None
        self.tool = POINTER
        self.toolbar.set_tool(POINTER)
        self.view = View(scale=1.0, fit=1.0, ox=0.0, oy=0.0, zoom=1.0)
        w, h = self._size_for_capture()
        self.set_default_size(w, h)
        self._prime_first_frame(w, h)
        self.present()
        self.area.grab_focus()

    def _prime_first_frame(self, w: int, h: int) -> None:
        self._recompute_fit(w, h)
        cache = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        self._paint_content(render.ctx(cache), w, h)
        self._cache = cache
        self._cache_key = (self.doc.rev, self.view.scale, self.view.ox,
                           self.view.oy, w, h, self.img)

    def _monitor_for_pointer(self):
        display = Gdk.Display.get_default()
        if display is None:
            return None, None
        x = y = None
        try:
            dev = display.get_default_seat().get_pointer()
            pt = dev.get_position()
            if hasattr(pt, "x"):
                x, y = pt.x, pt.y
            elif isinstance(pt, (tuple, list)) and len(pt) >= 2:
                x, y = pt[0], pt[1]
        except Exception:
            pass
        try:
            mon = (display.get_monitor_at_point(x, y) if x is not None
                   else display.get_monitors().get_item(0))
            return mon, mon.get_geometry() if mon is not None else None
        except Exception:
            return None, None

    def _size_for_capture(self) -> tuple[int, int]:
        _mon, geo = self._monitor_for_pointer()
        iw, ih = self.img.get_width(), self.img.get_height()
        chrome_x, chrome_y = 2 * PAD, 2 * PAD + TOOLBAR_SPACE
        screen_w, screen_h = (geo.width, geo.height) if geo else (1600, 1000)
        max_w = max(MIN_WINDOW_W, int(screen_w * MAX_SCREEN_SHARE))
        max_h = max(MIN_WINDOW_H, int(screen_h * MAX_SCREEN_SHARE))
        scale = min((max_w - chrome_x) / iw, (max_h - chrome_y) / ih, MAX_IMAGE_SCALE)
        self.view.fit = max(scale, MIN_IMAGE_SCALE)
        w = int(iw * self.view.fit) + chrome_x
        h = int(ih * self.view.fit) + chrome_y
        return min(max(w, MIN_WINDOW_W), max_w), min(max(h, MIN_WINDOW_H), max_h)

    # ----------------------------------------------------------------- view
    def _recompute_fit(self, w: int, h: int) -> None:
        if not self.img:
            return
        iw, ih = self.img.get_width(), self.img.get_height()
        # The window is already sized to the capture, so this only has to keep
        # the image inside the chrome if the size was clamped.
        avail_w = max(64, w - 2 * PAD)
        avail_h = max(64, h - 2 * PAD - TOOLBAR_SPACE)
        self.view.fit = min(avail_w / iw, avail_h / ih, MAX_IMAGE_SCALE)
        if self.view.zoom <= 1.0:
            self.view.scale = self.view.fit
            self.view.ox = (w - iw * self.view.scale) / 2
            self.view.oy = PAD
        else:
            self.view.scale = self.view.fit * self.view.zoom
            self._clamp_pan(w, h)

    def _clamp_pan(self, w: int, h: int) -> None:
        if not self.img:
            return
        iw = self.img.get_width() * self.view.scale
        ih = self.img.get_height() * self.view.scale
        margin = PAD
        self.view.ox = min(max(self.view.ox, margin - iw), max(margin - iw, w - iw - margin))
        lo, hi = margin - ih, h - TOOLBAR_SPACE - PAD - ih
        self.view.oy = min(max(self.view.oy, lo), max(lo, hi))

    def _zoom_at(self, factor: float, cx: float, cy: float, w: int, h: int) -> None:
        if not self.img:
            return
        bx, by = self.view.to_image(cx, cy)
        new_zoom = min(16.0, max(0.1, self.view.zoom * factor))
        if abs(new_zoom - self.view.zoom) < 1e-6:
            return
        self.view.zoom = new_zoom
        self._recompute_fit(w, h)
        if new_zoom > 1.0:
            # keep the point under the cursor anchored
            self.view.ox = cx - bx * self.view.scale
            self.view.oy = cy - by * self.view.scale
            self._clamp_pan(w, h)
        self._cache = None
        self.area.queue_draw()

    # ---------------------------------------------------------------- input
    def _on_motion(self, _ctl, _x, _y) -> None:
        """Pointer moved over the window: keep the toolbar awake."""
        self.toolbar.reveal()
        self._schedule_toolbar_idle()

    def _on_pointer_motion(self, _ctl, x, y) -> bool:
        self._last_xy = (x, y)
        if self._drag is None:
            return False
        return self._drag_to(x, y, shift=self._shift_down)

    def _on_press(self, gesture, _n_press, x, y) -> None:
        self.area.grab_focus()
        self.toolbar.reveal()
        self._schedule_toolbar_idle()
        try:
            btn = gesture.get_current_button()
        except Exception:
            btn = 1
        ix, iy = self.view.to_image(x, y)

        if btn in (2, 3) or (btn == 1 and self._space_down):
            self._drag = {"mode": "pan", "sx": x, "sy": y,
                         "ox": self.view.ox, "oy": self.view.oy}
            return

        if btn != 1:
            return

        if self.tool == TEXT:
            self._begin_text(ix, iy)
            self._drag = {"mode": "text"}
            return

        if self.tool == STEP:
            self.doc.mark()
            sh = Shape(kind=STEP, x=ix, y=iy, x2=ix, y2=iy, color=self.color,
                       size=SIZES[self.size_idx], step=self.doc.next_step())
            self.doc.add(sh, mark=False)
            self.doc.end_mark()
            self._invalidate()
            self.last_draw_tool = STEP
            self._drag = {"mode": "step"}
            return

        if self.tool == SELECT:
            tol = 6.0 / self.view.scale
            hit = self.doc.pick(ix, iy, tol)
            self.selected = hit
            if hit is not None:
                self.doc.mark()
                self._drag = {"mode": "move", "shape": hit, "start": hit.copy(),
                              "ix": ix, "iy": iy}
            else:
                self._drag = {"mode": "band", "ix": ix, "iy": iy}
            self.area.queue_draw()
            return

        self.doc.mark()
        if self.tool == FREEHAND:
            sh = Shape(kind=FREEHAND, color=self.color,
                       width=WIDTHS[self.width_idx], points=[(ix, iy)])
        else:
            sh = Shape(kind=self.tool, x=ix, y=iy, x2=ix, y2=iy,
                       color=self.color, width=WIDTHS[self.width_idx])
            if self.tool == BLUR:
                sh.blur_mode = self.app.blur_mode
                # Keep the mosaic visually constant as you zoom.
                sh.block = max(3.0, 9.0 / self.view.scale)
        self._preview = sh
        self._drag = {"mode": "draw", "ix": ix, "iy": iy}
        self.last_draw_tool = self.tool

    def _drag_to(self, x: float, y: float, shift: bool) -> bool:
        d = self._drag
        if d is None:
            return False
        mode = d["mode"]
        if mode == "pan":
            self.view.ox = d["ox"] + (x - d["sx"])
            self.view.oy = d["oy"] + (y - d["sy"])
            self._clamp_pan(self.area.get_width(), self.area.get_height())
            self._cache = None
            self.area.queue_draw()
            return True
        if mode == "move":
            ix, iy = self.view.to_image(x, y)
            s, base = d["shape"], d["start"]
            sdx, sdy = ix - d["ix"], iy - d["iy"]
            s.x, s.y = base.x + sdx, base.y + sdy
            s.x2, s.y2 = base.x2 + sdx, base.y2 + sdy
            if s.points:
                s.points = [(px + sdx, py + sdy) for px, py in base.points]
            self.area.queue_draw()
            return True
        if mode == "band":
            ix, iy = self.view.to_image(x, y)
            self._band = (d["ix"], d["iy"], ix, iy)
            self.area.queue_draw()
            return True
        if mode != "draw":
            return False

        sh = self._preview
        if sh is None:
            return False
        ix, iy = self.view.to_image(x, y)
        if sh.kind == FREEHAND:
            last = sh.points[-1]
            if (ix - last[0]) ** 2 + (iy - last[1]) ** 2 > (1.5 / self.view.scale) ** 2:
                sh.points.append((ix, iy))
        else:
            if shift:
                # Constrain to 45-degree increments.
                dx, dy = ix - sh.x, iy - sh.y
                ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(dx, dy)
                ix = sh.x + length * math.cos(ang)
                iy = sh.y + length * math.sin(ang)
            sh.x2, sh.y2 = ix, iy
        self.area.queue_draw()
        return True

    def _on_release(self, _gesture, _n_press, x, y) -> None:
        d, self._drag = self._drag, None
        if d is None:
            return
        mode = d["mode"]
        if mode in ("pan", "text", "step"):
            return
        if mode == "band":
            band, self._band = getattr(self, "_band", None), None
            if band:
                hits = self.doc.pick_box(min(band[0], band[2]), min(band[1], band[3]),
                                         max(band[0], band[2]), max(band[1], band[3]))
                self.selected = hits[-1] if hits else None
            self.area.queue_draw()
            return
        if mode == "move":
            s, start = d["shape"], d["start"]
            moved = (s.x, s.y, s.x2, s.y2) != (start.x, start.y, start.x2, start.y2)
            if moved:
                self.doc.end_mark()
                if s.kind == STEP:
                    self.doc.renumber_steps()
            else:
                self.doc._undo.pop()  # click without movement: no history entry
            self.area.queue_draw()
            return

        # finishing a drawn shape
        sh = self._preview
        self._preview = None
        if sh is None:
            return
        if sh.kind != FREEHAND:
            ix, iy = self.view.to_image(x, y)
            sh.x2, sh.y2 = ix, iy
        if sh.kind == POINTER:
            sh.x2, sh.y2 = sh.x, sh.y   # a tap places the cursor glyph
        drew = (abs(sh.x2 - sh.x) > 1.0 and abs(sh.y2 - sh.y) > 1.0) if sh.kind != FREEHAND \
            else len(sh.points) > 1
        if drew or sh.kind == POINTER:
            self.doc.add(sh, mark=False)
        self.doc.end_mark()
        self.area.queue_draw()

    def _on_scroll(self, _ctl, dx: float, dy: float) -> bool:
        if dy == 0:
            dy = dx
        if dy == 0:
            return False
        w, h = self.area.get_width(), self.area.get_height()
        # Anchor the zoom on the pointer when we have a recent position.
        px, py = getattr(self, "_last_xy", (w / 2, h / 2))
        factor = 1.12 if dy < 0 else 1 / 1.12
        self._zoom_at(factor, px, py, w, h)
        return True

    # ----------------------------------------------------------------- help
    def _build_help(self) -> Gtk.Box:
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER,
                       valign=Gtk.Align.CENTER)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.add_css_class("qs-help")
        title = Gtk.Label(label="Quickshot")
        title.set_halign(Gtk.Align.START)
        panel.append(title)

        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        for heading, rows in HELP_ROWS:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            col.add_css_class("col")
            head = Gtk.Label(label=heading)
            head.set_halign(Gtk.Align.START)
            head.add_css_class("k")
            col.append(head)
            for key, desc in rows:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                k = Gtk.Label(label=key)
                k.add_css_class("k")
                d = Gtk.Label(label=desc)
                row.append(k)
                row.append(d)
                col.append(row)
            cols.append(col)
        panel.append(cols)

        foot = Gtk.Label(label="Enter copies to the clipboard and closes  •  Esc discards")
        foot.add_css_class("foot")
        foot.set_halign(Gtk.Align.START)
        panel.append(foot)

        wrap.append(panel)
        return wrap

    # ----------------------------------------------------------------- text
    def _build_entry(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("qs-entry-frame")
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Type, then Enter")
        self.entry.set_width_chars(22)
        self.entry.add_css_class("qs-entry")
        frame.append(self.entry)
        hint = Gtk.Label(label="Enter to place  •  Esc to cancel")
        hint.add_css_class("qs-entry-hint")
        frame.append(hint)
        box.append(frame)
        box.set_visible(False)
        self.entry.connect("changed", self._on_entry_changed)
        self.entry.connect("activate", self._on_entry_commit)
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_entry_key)
        self.entry.add_controller(kc)
        return box

    def _begin_text(self, ix: float, iy: float) -> None:
        sh = Shape(kind=TEXT, x=ix, y=iy, x2=ix, y2=iy, color=self.color,
                   size=SIZES[self.size_idx], text="")
        self._entry_pending = sh
        lx, ly = self.view.to_logical(ix, iy)
        self.entry_frame.set_visible(True)
        w, h = self.area.get_width(), self.area.get_height()
        w = min(self.entry.get_width() or 260, 340)
        self.entry_frame.set_halign(Gtk.Align.START)
        self.entry_frame.set_valign(Gtk.Align.START)
        self.entry_frame.set_margin_start(int(max(12, min(lx, w - 20))))
        self.entry_frame.set_margin_top(int(max(12, min(ly, h - 120))))
        self.entry.set_text("")
        self.entry.grab_focus()
        self.last_draw_tool = TEXT

    def _on_entry_changed(self, entry) -> None:
        if self._entry_pending is not None:
            self._entry_pending.text = entry.get_text()
            self.area.queue_draw()

    def _on_entry_commit(self, _entry) -> None:
        sh = self._entry_pending
        self._cancel_entry()
        if sh is None:
            return
        txt = sh.text.strip()
        if not txt:
            return
        self.doc.mark()
        self.doc.add(sh, mark=False)
        self.doc.end_mark()
        self.area.queue_draw()

    def _on_entry_key(self, _ctl, keyval, _kc, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._cancel_entry()
            return True
        return False

    def _cancel_entry(self) -> None:
        self._entry_pending = None
        self.entry_frame.set_visible(False)
        self.area.queue_draw()
        self.area.grab_focus()

    # ----------------------------------------------------------------- draw
    def _on_draw(self, _area, cr, width, height) -> None:
        cr.set_source_rgb(0.051, 0.051, 0.063)
        cr.paint()
        if not self.img:
            return
        if self._cache_key != (self.doc.rev, self.view.scale, self.view.ox,
                               self.view.oy, width, height, self.img):
            self._recompute_fit(width, height)
            self._cache = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            cc = render.ctx(self._cache)
            self._paint_content(cc, width, height)
            self._cache_key = (self.doc.rev, self.view.scale, self.view.ox,
                               self.view.oy, width, height, self.img)
        cr.set_source_surface(self._cache, 0, 0)
        cr.paint()

        # live layer
        self.view.apply(cr)
        if self._preview is not None:
            render.draw_shape(cr, self.img, self._preview, self.view)
        if self.selected is not None and self._drag is None:
            render.draw_shape(cr, self.img, self.selected, self.view, selected=True)
        if self._entry_pending is not None and self._entry_pending.text:
            render.draw_shape(cr, self.img, self._entry_pending, self.view)
        cr.restore()

        band = getattr(self, "_band", None)
        if band:
            x0, y0 = self.view.to_logical(band[0], band[1])
            x1, y1 = self.view.to_logical(band[2], band[3])
            cr.set_source_rgba(0.235, 0.651, 0.969, 0.25)
            cr.rectangle(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            cr.fill_preserve()
            cr.set_source_rgba(0.235, 0.651, 0.969, 0.9)
            cr.set_line_width(1.2)
            cr.stroke()

        # 1px frame around the screenshot
        iw = self.img.get_width() * self.view.scale
        ih = self.img.get_height() * self.view.scale
        cr.set_source_rgba(1, 1, 1, 0.10)
        cr.set_line_width(1)
        cr.rectangle(self.view.ox - 0.5, self.view.oy - 0.5, iw + 1, ih + 1)
        cr.stroke()

    def _paint_content(self, cc: cairo.Context, width: int, height: int) -> None:
        self.view.apply(cc)
        cc.set_source_surface(self.img, 0, 0)
        cc.paint()
        for s in self.doc.shapes:
            render.draw_shape(cc, self.img, s, self.view)
        cc.restore()

    def queue_draw(self) -> None:
        self.area.queue_draw()

    def _invalidate(self) -> None:
        self._cache_key = None
        self.area.queue_draw()

    # ------------------------------------------------------------- commands
    def set_tool(self, tool: str) -> None:
        self.tool = tool
        if tool in TOOLS:
            self.last_draw_tool = tool
        self.toolbar.set_tool(tool)
        try:
            self.area.set_cursor(Gdk.Cursor.new_from_name(CURSORS.get(tool, "default")))
        except Exception:
            pass

    def set_color(self, color) -> None:
        self.color = color
        self.toolbar.set_color(color)
        if self.selected is not None:
            self.doc.mark()
            self.selected.color = color
            self.doc.end_mark()
        self._invalidate()

    def _cycle_color(self, back: bool = False) -> None:
        try:
            i = PALETTE.index(self.color)
        except ValueError:
            i = 0
        i = (i - 1 if back else i + 1) % len(PALETTE)
        self.set_color(PALETTE[i])

    def _adjust(self, attr: str, idx_attr: str, seq: list, delta: int) -> None:
        setattr(self, idx_attr, max(0, min(len(seq) - 1, getattr(self, idx_attr) + delta)))
        if self.selected is not None:
            self.doc.mark()
            setattr(self.selected, attr, seq[getattr(self, idx_attr)])
            self.doc.end_mark()
            self._invalidate()

    def do_undo(self) -> None:
        if self.doc.undo():
            self.selected = None
            self._invalidate()

    def do_redo(self) -> None:
        if self.doc.redo():
            self.selected = None
            self._invalidate()

    def delete_selected(self) -> None:
        if self.selected is not None:
            self.doc.remove(self.selected)
            self.selected = None
            self._invalidate()

    def composite(self) -> cairo.ImageSurface:
        """Flatten base image + annotations at the on-screen relative scale."""
        iw, ih = self.img.get_width(), self.img.get_height()
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, iw, ih)
        c = render.ctx(out)
        c.set_source_surface(self.img, 0, 0)
        c.paint()
        # u == 1/scale, so a scale of `fit` reproduces the on-screen thickness.
        ev = View(scale=self.view.fit or 1.0, fit=self.view.fit or 1.0,
                  ox=0.0, oy=0.0, zoom=1.0)
        for s in self.doc.shapes:
            render.draw_shape(c, self.img, s, ev)
        return out

    def commit_copy(self) -> None:
        if self._closing:
            return
        try:
            imageio.copy_to_clipboard(self.composite())
        except Exception as exc:
            self.app.notify_error(f"clipboard: {exc}")
        self._close()

    def commit_save(self) -> None:
        if self._closing:
            return
        try:
            path = imageio.save_png(
                self.composite(),
                os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots"),
            )
            self.app.notify(f"Saved {path}")
        except Exception as exc:
            self.app.notify_error(f"save: {exc}")
        self._close()

    def discard_file(self, path: str) -> None:
        """Delete a cached capture that never made it into the editor."""
        try:
            os.remove(path)
        except OSError:
            pass

    def reset(self) -> None:
        """Return the editor to a clean, hidden, empty state.

        Used when the window is flagged visible but holds no image, which
        otherwise makes every subsequent capture request a silent no-op.
        """
        self.entry_frame.set_visible(False)
        self.help_box.set_visible(False)
        self._preview = None
        self._drag = None
        self._band = None
        self.selected = None
        self._cache = None
        self._cache_key = None
        self.img = None
        self.doc = Doc()
        self._path = None
        self._closing = True
        self.hide()

    def dismiss(self) -> None:
        if self._entry_pending is not None:
            self._cancel_entry()
            return
        if self.help_box.get_visible():
            self.help_box.set_visible(False)
            return
        self._close()

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._path:
            self.discard_file(self._path)
        self._path = None
        self.img = None
        self.doc = Doc()
        self._preview = None
        self.selected = None
        self._cache = None
        self._cache_key = None
        self._band = None
        self.entry_frame.set_visible(False)
        self.help_box.set_visible(False)
        self.hide()
        self.app.on_editor_closed()

    def toggle_help(self) -> None:
        self.help_box.set_visible(not self.help_box.get_visible())
        self._schedule_toolbar_idle()

    def _schedule_toolbar_idle(self) -> None:
        self.toolbar.schedule_idle()

    # ----------------------------------------------------------------- keys
    def _on_key_release(self, _ctl, keyval, _keycode, _state) -> bool:
        if keyval == Gdk.KEY_space:
            self._space_down = False
            return True
        if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            self._shift_down = False
        return False

    def _on_key(self, _ctl, keyval, _keycode, state) -> bool:
        if self._entry_pending is not None:
            return False  # the entry has focus
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if keyval == Gdk.KEY_space:
            self._space_down = True
            return True
        if keyval in (Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            self._shift_down = True
            return False
        if keyval == Gdk.KEY_Escape:
            self.dismiss()
            return True
        if ctrl and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.commit_save()
            return True
        if ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            self.do_redo() if shift else self.do_undo()
            return True
        if ctrl and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self.do_redo()
            return True
        if ctrl:
            return False
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            self.commit_copy()
            return True
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self.delete_selected()
            return True
        if keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self.toggle_help()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C):
            # Accept the shifted or unshifted keyval: some layouts report the
            # unshifted code even while Shift is held.
            self._cycle_color(back=shift)
            return True
        if keyval in (Gdk.KEY_b, Gdk.KEY_B) and shift:
            self.app.blur_mode = "blur" if self.app.blur_mode == "mosaic" else "mosaic"
            self.app.notify(f"Redact: {self.app.blur_mode}")
            return True
        if keyval in (Gdk.KEY_comma, Gdk.KEY_less):
            self._adjust("width", "width_idx", WIDTHS, -1)
            return True
        if keyval in (Gdk.KEY_period, Gdk.KEY_greater):
            self._adjust("width", "width_idx", WIDTHS, 1)
            return True
        if keyval in (Gdk.KEY_bracketleft, Gdk.KEY_braceleft):
            self._adjust("size", "size_idx", SIZES, -1)
            return True
        if keyval == Gdk.KEY_bracketright:
            self._adjust("size", "size_idx", SIZES, 1)
            return True
        if keyval in (Gdk.KEY_equal, Gdk.KEY_KP_Add, Gdk.KEY_plus):
            self._zoom_at(1.25, self.area.get_width() / 2, self.area.get_height() / 2,
                          self.area.get_width(), self.area.get_height())
            return True
        if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract, Gdk.KEY_underscore):
            self._zoom_at(1 / 1.25, self.area.get_width() / 2, self.area.get_height() / 2,
                          self.area.get_width(), self.area.get_height())
            return True
        if keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.view.zoom = 1.0
            self._cache = None
            self.area.queue_draw()
            return True
        if keyval == Gdk.KEY_Tab:
            self.set_tool(SELECT if self.tool != SELECT else self.last_draw_tool)
            return True
        # arrows nudge the selection
        nudge = {Gdk.KEY_Left: (-1, 0), Gdk.KEY_Right: (1, 0),
                 Gdk.KEY_Up: (0, -1), Gdk.KEY_Down: (0, 1)}.get(keyval)
        if nudge and self.selected is not None:
            self.doc.mark()
            step = 10.0 if shift else 1.0
            self.selected.translate(nudge[0] * step, nudge[1] * step)
            self.doc.end_mark()
            self._invalidate()
            return True
        # tools
        tools = {
            Gdk.KEY_p: POINTER, Gdk.KEY_r: RECT, Gdk.KEY_o: ELLIPSE,
            Gdk.KEY_l: LINE, Gdk.KEY_d: FREEHAND, Gdk.KEY_t: TEXT,
            Gdk.KEY_b: BLUR, Gdk.KEY_n: STEP, Gdk.KEY_v: SELECT,
        }
        if keyval in tools:
            self.set_tool(tools[keyval])
            return True
        return False
