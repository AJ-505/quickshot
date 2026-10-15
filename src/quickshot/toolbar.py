"""The floating tool bar at the bottom of the editor.

Keyboard-first: every button shows the single key that does the same thing, so
the tool bar is a discovery surface rather than something you have to aim at.
"""
from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from . import icons
from .model import PALETTE, SELECT, TOOLS
from .style import CSS

TOOL_LABELS = {
    "pointer": "Arrow",
    "cursor": "Mouse cursor",
    "rect": "Rectangle",
    "ellipse": "Ellipse",
    "line": "Line",
    "freehand": "Freehand",
    "text": "Text",
    "blur": "Redact (mosaic)",
    "step": "Numbered step",
    "select": "Select / move",
}

TOOL_KEYS = {
    "pointer": "P", "cursor": "M", "rect": "R", "ellipse": "O", "line": "L",
    "freehand": "D", "text": "T", "blur": "B", "step": "N", "select": "V",
}


def _keyed(child: Gtk.Widget, hint: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    box.append(child)
    box.append(Gtk.Label(label=hint, css_classes=["qs-key"]))
    return box


def _icon(name: str) -> Gtk.Image:
    img = Gtk.Image.new_from_paintable(icons.icon(name))
    img.set_pixel_size(20)
    return img


class Swatch(Gtk.DrawingArea):
    """A round colour chip."""

    def __init__(self, color, size: int = 18, current: bool = False) -> None:
        super().__init__()
        self.color = color
        self.current = current
        self.set_content_width(size)
        self.set_content_height(size)
        self.add_css_class("qs-swatch")
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, w, h) -> None:
        import cairo
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        r, g, b, a = self.color
        cr.set_source_rgba(r, g, b, a)
        cr.arc(w / 2, h / 2, min(w, h) / 2 - 3, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.3)
        cr.set_line_width(1)
        cr.stroke()
        if self.current:
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.set_line_width(1.5)
            cr.arc(w / 2, h / 2, min(w, h) / 2 - 0.75, 0, 2 * math.pi)
            cr.stroke()


class StrokeSample(Gtk.DrawingArea):
    """A pill showing the current stroke width in the current colour."""

    def __init__(self) -> None:
        super().__init__()
        self.color = PALETTE[0]
        self.width = 5.0
        self.set_content_width(24)
        self.set_content_height(20)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, w, h) -> None:
        r, g, b, a = self.color
        t = max(2.0, min(self.width, h - 2))
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.set_line_cap(1)
        cr.set_line_width(t + 2)
        cr.move_to(t / 2 + 2, h / 2)
        cr.line_to(w - t / 2 - 2, h / 2)
        cr.stroke_preserve()
        cr.set_source_rgba(r, g, b, a)
        cr.set_line_width(t)
        cr.stroke()


class Toolbar(Gtk.Box):
    IDLE_MS = 2600

    def __init__(self, editor) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.editor = editor
        self._pop: Gtk.Popover | None = None
        self._hide_timer_active = False
        self._timer = 0
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_margin_bottom(18)
        self.add_css_class("qs-toolbar")

        self.tool_buttons: dict[str, Gtk.ToggleButton] = {}
        for tool in TOOLS + [SELECT]:
            b = Gtk.ToggleButton()
            b.set_child(_keyed(_icon(tool), TOOL_KEYS[tool]))
            b.add_css_class("qs-tool")
            b.set_tooltip_text(f"{TOOL_LABELS[tool]}  ({TOOL_KEYS[tool]})")
            b.connect("toggled", self._on_tool_toggled, tool)
            self.append(b)
            self.tool_buttons[tool] = b

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Colour picker
        self.color_button = Gtk.Button()
        self.swatch = Swatch(PALETTE[0], 20, current=True)
        self.color_button.set_child(_keyed(self.swatch, "C"))
        self.color_button.add_css_class("qs-tool")
        self.color_button.set_tooltip_text("Colour  (C to cycle)")
        self.color_button.connect("clicked", self._on_color_clicked)
        self.append(self.color_button)

        self.stroke = StrokeSample()
        stroke_box = _keyed(self.stroke, ", .")
        stroke_box.add_css_class("qs-stroke")
        stroke_box.set_tooltip_text("Stroke width  ( , and . )")
        self.append(stroke_box)

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.append(self._action("undo", "Undo  (Ctrl+Z)", "^Z", lambda: self.editor.do_undo()))
        self.append(self._action("redo", "Redo  (Ctrl+Shift+Z)", "^⇧Z", lambda: self.editor.do_redo()))

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.append(self._action("copy", "Copy to clipboard  (Enter)", "Enter", self.editor.commit_copy, "qs-primary"))
        self.append(self._action("save", "Save to file  (Ctrl+S)", "^S", self.editor.commit_save))

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.append(self._action("help", "Shortcuts  (H)", "H", self.editor.toggle_help))
        self.append(self._action("close", "Discard  (Esc)", "Esc", self.editor.dismiss, "qs-danger"))

    def _action(self, name, tip, hint, cb, extra: str = "") -> Gtk.Button:
        b = Gtk.Button()
        b.set_child(_keyed(_icon(name), hint))
        b.add_css_class("qs-tool")
        if extra:
            b.add_css_class(extra)
        b.set_tooltip_text(tip)
        b.connect("clicked", lambda *_: cb())
        return b

    # -- tool selection --------------------------------------------------
    def _on_tool_toggled(self, btn: Gtk.ToggleButton, tool: str) -> None:
        if btn.get_active():
            self.editor.set_tool(tool)

    def set_tool(self, tool: str) -> None:
        for name, b in self.tool_buttons.items():
            want = name == tool
            if b.get_active() != want:
                b.set_active(want)

    # -- colour ----------------------------------------------------------
    def set_color(self, color) -> None:
        self.swatch.color = color
        self.swatch.queue_draw()
        self.stroke.color = color
        self.stroke.queue_draw()

    def set_width(self, width: float) -> None:
        self.stroke.width = width
        self.stroke.queue_draw()

    # -- auto-hide -------------------------------------------------------
    def schedule_idle(self) -> None:
        """No-op.

        The bar used to fade out when the pointer went still. An opacity
        animation on a floating panel is a brightness change in the user's
        peripheral vision, which reads as flicker, so the bar now stays put.
        The methods remain so callers do not need to care.
        """

    def reveal(self) -> None:
        """No-op; the bar is always fully visible."""

    def _on_color_clicked(self, _b) -> None:
        if self._pop is not None:
            self._pop.unparent()
        self._pop = self._build_color_popover()
        self._pop.set_parent(self.color_button)
        self._pop.popup()

    def _build_color_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        pop.add_css_class("qs-popover")
        grid = Gtk.Grid(column_spacing=6, row_spacing=6, margin_top=10,
                        margin_bottom=10, margin_start=10, margin_end=10)
        for i, c in enumerate(PALETTE):
            b = Gtk.Button()
            b.set_child(Swatch(c, 28, current=c == self.editor.color))
            b.add_css_class("qs-color")
            b.connect("clicked", lambda _x, col=c, p=pop: (self.editor.set_color(col), p.popdown()))
            grid.attach(b, i % 3, i // 3, 1, 1)
        pop.set_child(grid)
        return pop


def install_css() -> None:
    prov = Gtk.CssProvider()
    if isinstance(CSS, bytes):
        prov.load_from_data(CSS)
    else:
        prov.load_from_string(CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
