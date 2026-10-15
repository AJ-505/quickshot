"""Cairo rendering for the editor canvas.

Everything is drawn in *image pixel* space: the caller sets up a transform of
`translate(ox, oy); scale(s, s)`. Logical-pixel quantities (stroke widths, font
sizes, radii) are divided by the fit scale so they keep a constant apparent size
regardless of zoom.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Pango, PangoCairo, GdkPixbuf  # noqa: E402

from .model import BLUR, ELLIPSE, FREEHAND, LINE, POINTER, RECT, STEP, TEXT, Shape  # noqa: E402


def ctx(surface: cairo.ImageSurface) -> cairo.Context:
    """A drawing context for an image surface.

    Constructing the Context is the portable spelling: pycairo 1.27 dropped
    `ImageSurface.get_context()` and its replacement `get_content()` returns an
    unrelated `Content` value type.
    """
    return cairo.Context(surface)


@dataclass
class View:
    """Maps image pixels to window (logical) pixels."""

    scale: float   # image px -> logical px, includes zoom
    fit: float     # image px -> logical px at zoom 1
    ox: float      # logical px offset of the image origin
    oy: float
    zoom: float = 1.0

    def to_logical(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + x * self.scale, self.oy + y * self.scale

    def to_image(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.ox) / self.scale, (y - self.oy) / self.scale

    def apply(self, cr: cairo.Context) -> None:
        cr.save()
        cr.translate(self.ox, self.oy)
        cr.scale(self.scale, self.scale)


def _u(view: View) -> float:
    """One logical pixel expressed in image pixels."""
    return 1.0 / (view.scale or 1.0)


# ---------------------------------------------------------------- transforms


def _smoothed(cr: cairo.Context, points: list) -> None:
    """Catmull-Rom style smoothing so freehand does not look faceted."""
    if len(points) < 2:
        return
    if len(points) == 2:
        cr.move_to(*points[0])
        cr.line_to(*points[1])
        return
    cr.move_to(*points[0])
    n = len(points)
    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        cr.curve_to(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])


# ------------------------------------------------------------------ redaction


def _set_filter(cr: cairo.Context, f) -> None:
    """Filter control moved from Context to Pattern in pycairo 1.27."""
    try:
        cr.pattern_set_filter(f)
    except AttributeError:
        cr.get_source().set_filter(f)


def _set_extend_pad(cr: cairo.Context) -> None:
    """Replicate edge pixels outside the source.

    Without this, a bilinear magnification samples half a source pixel beyond
    each edge; with the default EXTEND_NONE those samples are transparent, so
    the patch comes out with a semi-transparent rim (measured: alpha 37).
    """
    try:
        cr.pattern_set_extend(cairo.EXTEND_PAD)
    except AttributeError:
        cr.get_source().set_extend(cairo.EXTEND_PAD)


def _downscale(src: cairo.ImageSurface, w: int, h: int, box: tuple) -> cairo.ImageSurface:
    """Draw `src` into a (w, h) surface, filtered."""
    x, y = box[0], box[1]
    tmp = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    c = ctx(tmp)
    c.set_source_surface(src, -x, -y)
    _set_filter(c, cairo.FILTER_GOOD)
    c.paint()
    return tmp


# ------------------------------------------------------- surface <-> pixbuf
# Cairo ARGB32 is premultiplied BGRA in memory; GdkPixbuf RGB8 wants R,G,B.
# Screenshots are opaque, so alpha is dropped and these stay at C speed.

def _swizzle(bgra: bytes, w: int, h: int, stride: int) -> bytes:
    if stride == w * 4:
        b = bytearray(w * h * 3)
        b[0::3] = bgra[2::4]
        b[1::3] = bgra[1::4]
        b[2::3] = bgra[0::4]
        return bytes(b)
    out = bytearray(w * h * 3)
    for y in range(h):
        src = y * stride
        dst = y * w * 3
        row = bgra[src:src + w * 4]
        out[dst:dst + w * 3] = bytes(b"".join(
            (row[i + 2:i + 3] + row[i + 1:i + 2] + row[i:i + 1]) for i in range(0, w * 4, 4)
        ))
    return bytes(out)


def _unswizzle(rgb: bytes, w: int, h: int, stride: int) -> cairo.ImageSurface:
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    dst = bytearray(w * h * 4)
    for y in range(h):
        s = y * stride
        row = rgb[s:s + w * 3]
        d = y * w * 4
        buf = bytearray(w * 4)
        buf[0::4] = row[2::3]
        buf[1::4] = row[1::3]
        buf[2::4] = row[0::3]
        buf[3::4] = b"\xff" * w
        dst[d:d + w * 4] = buf
    surf.get_data()[:] = dst
    surf.mark_dirty()
    return surf


def _area_reduce(region: cairo.ImageSurface, tw: int, th: int) -> cairo.ImageSurface:
    """Box-average `region` down to (tw, th).

    Cairo cannot do this: its filters interpolate between samples rather than
    averaging, so a 9x reduction point-samples and drops thin strokes -- text
    stays legible, which defeats the whole purpose. GdkPixbuf's BILINEAR scaler
    is a real area average, and it ships with GTK.
    """
    region.flush()
    w, h = region.get_width(), region.get_height()
    rgb = _swizzle(bytes(region.get_data()), w, h, region.get_stride())
    pb = GdkPixbuf.Pixbuf.new_from_data(
        rgb, GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3
    )
    small = pb.scale_simple(tw, th, GdkPixbuf.InterpType.BILINEAR)
    return _unswizzle(bytes(small.get_pixels()), small.get_width(),
                      small.get_height(), small.get_rowstride())


def _magnify(small: cairo.ImageSurface, w: int, h: int, nearest: bool) -> cairo.ImageSurface:
    """Grow `small` to (w, h). Upscaling is the direction cairo filters do well."""
    sw, sh = small.get_width(), small.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    c = ctx(out)
    if not nearest:
        # Two bilinear steps approximate a smooth kernel; one step alone
        # leaves visible facets.
        mid = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(sw, w // 3), max(sh, h // 3))
        mc = ctx(mid)
        mc.scale(mid.get_width() / sw, mid.get_height() / sh)
        mc.set_source_surface(small, 0, 0)
        _set_filter(mc, cairo.FILTER_BILINEAR)
        _set_extend_pad(mc)
        mc.paint()
        sw, sh = mid.get_width(), mid.get_height()
        small = mid
    c.scale(w / sw, h / sh)
    c.set_source_surface(small, 0, 0)
    _set_filter(c, cairo.FILTER_NEAREST if nearest else cairo.FILTER_BILINEAR)
    _set_extend_pad(c)
    c.paint()
    return out


_REDACT_CACHE: dict = {}
_REDACT_CACHE_MAX = 12


def clamped_bounds(img: cairo.ImageSurface, shape: Shape) -> tuple[int, int, int, int]:
    """Shape box intersected with the image, as integer pixel bounds."""
    x0, y0, x1, y1 = shape.bounds()
    return (max(0, int(math.floor(x0))),
            max(0, int(math.floor(y0))),
            min(img.get_width(), int(math.ceil(x1))),
            min(img.get_height(), int(math.ceil(y1))))


def redact(img: cairo.ImageSurface, shape: Shape) -> cairo.ImageSurface:
    """Return an opaque, blurred-or-pixelated patch for the shape's box.

    Results are memoised on the region and its parameters, because a redaction
    is regenerated on every frame while it is being dragged. Use
    `clamped_bounds` for the placement, so a box dragged off the edge of the
    screenshot still lines up.
    """
    x0, y0, x1, y1 = clamped_bounds(img, shape)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)

    key = (id(img), x0, y0, w, h, shape.blur_mode, round(shape.block, 2))
    hit = _REDACT_CACHE.get(key)
    if hit is not None:
        return hit

    region = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    rc = ctx(region)
    rc.set_source_surface(img, -x0, -y0)
    rc.paint()

    if shape.blur_mode == "blur":
        small = _area_reduce(region, max(1, w // 18), max(1, h // 18))
        out = _magnify(small, w, h, nearest=False)
    else:  # mosaic / pixelate
        b = max(1.0, shape.block)
        small = _area_reduce(region, max(1, int(w / b)), max(1, int(h / b)))
        out = _magnify(small, w, h, nearest=True)

    if len(_REDACT_CACHE) >= _REDACT_CACHE_MAX:
        _REDACT_CACHE.pop(next(iter(_REDACT_CACHE)))
    _REDACT_CACHE[key] = out
    return out


# ----------------------------------------------------------------- primitives


def _arrow(cr: cairo.Context, s: Shape, u: float) -> None:
    w = s.width * u
    x1, y1, x2, y2 = s.x, s.y, s.x2, s.y2
    ang = math.atan2(y2 - y1, x2 - x1)
    head = max(w * 3.0, 13.0 * u)
    bx, by = x2 - head * math.cos(ang), y2 - head * math.sin(ang)
    cr.set_source_rgba(*s.color)
    cr.set_line_width(w)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x1, y1)
    cr.line_to(bx, by)
    cr.stroke()
    spread = 0.42
    cr.move_to(x2, y2)
    cr.line_to(x2 - head * math.cos(ang - spread), y2 - head * math.sin(ang - spread))
    cr.line_to(x2 - head * math.cos(ang + spread), y2 - head * math.sin(ang + spread))
    cr.close_path()
    cr.fill_preserve()
    cr.set_line_width(w * 0.6)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.stroke()


def _cursor_pointer(cr: cairo.Context, s: Shape, u: float) -> None:
    """Classic mouse-pointer glyph, tip at (x, y)."""
    S = max(6.0 * u, (s.size * 1.6) * u)
    pts = [
        (0.00, 0.00), (0.00, 0.78), (0.22, 0.60), (0.36, 0.96),
        (0.50, 0.91), (0.36, 0.55), (0.62, 0.53),
    ]
    cr.new_path()
    cr.move_to(s.x, s.y)
    for fx, fy in pts[1:]:
        cr.line_to(s.x + fx * S, s.y + fy * S)
    cr.close_path()
    cr.set_source_rgba(1, 1, 1, 0.95)
    cr.fill_preserve()
    cr.set_source_rgba(0, 0, 0, 0.85)
    cr.set_line_width(1.6 * u)
    cr.stroke()


def _step(cr: cairo.Context, s: Shape, u: float) -> None:
    cx, cy = (s.x + s.x2) / 2, (s.y + s.y2) / 2
    r = s.size * u
    cr.set_source_rgba(*s.color)
    cr.arc(cx, cy, r, 0, 2 * math.pi)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.28)
    cr.set_line_width(1.5 * u)
    cr.stroke()
    cr.save()
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(r * 1.25)
    ext = cr.text_extents(str(s.step))
    cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy - ext.height / 2 - ext.y_bearing)
    cr.set_source_rgba(1, 1, 1, 1)
    cr.show_text(str(s.step))
    cr.restore()


def _text(cr: cairo.Context, s: Shape, u: float) -> None:
    if not s.text:
        return
    fs = max(6.0, s.size * u)
    layout = PangoCairo.create_layout(cr)
    # `set_absolute_size` is in Pango units and is independent of the DPI
    # setting, so the glyph size tracks our zoom transform exactly.
    desc = Pango.FontDescription.from_string("Sans Bold")
    desc.set_absolute_size(fs * Pango.SCALE)
    layout.set_font_description(desc)
    layout.set_text(s.text, -1)
    pw, ph = layout.get_pixel_size()
    lw, lh = layout.get_size()  # pango units

    # Halo so text stays readable on any background.
    cr.save()
    cr.set_source_rgba(0, 0, 0, 0.45)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        cr.move_to(s.x + dx * 1.6 * u, s.y + dy * 1.6 * u)
        PangoCairo.show_layout(cr, layout)
    cr.set_source_rgba(*s.color)
    cr.move_to(s.x, s.y)
    PangoCairo.show_layout(cr, layout)
    cr.restore()
    s.x2 = s.x + pw
    s.y2 = s.y + ph


# --------------------------------------------------------------------- shapes


def draw_shape(cr: cairo.Context, img: cairo.ImageSurface, s: Shape, view: View,
               selected: bool = False) -> None:
    u = _u(view)
    cr.save()
    if s.kind == BLUR:
        bx0, by0, bx1, by1 = clamped_bounds(img, s)
        patch = redact(img, s)
        cr.set_source_surface(patch, bx0, by0)
        cr.paint()
        cr.set_source_rgba(1, 1, 1, 0.22)
        cr.set_line_width(1.2 * u)
        cr.rectangle(bx0, by0, bx1 - bx0, by1 - by0)
        cr.stroke()
        cr.restore()
        return

    if s.kind == FREEHAND:
        cr.set_source_rgba(*s.color)
        cr.set_line_width(s.width * u)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        _smoothed(cr, s.points)
        cr.stroke()
    elif s.kind == POINTER:
        if math.hypot(s.x2 - s.x, s.y2 - s.y) < 6 * u:
            _cursor_pointer(cr, s, u)
        else:
            _arrow(cr, s, u)
    elif s.kind == STEP:
        _step(cr, s, u)
    elif s.kind == TEXT:
        _text(cr, s, u)
    else:
        cr.set_source_rgba(*s.color)
        cr.set_line_width(s.width * u)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if s.kind == RECT:
            cr.rectangle(s.x, s.y, s.x2 - s.x, s.y2 - s.y)
            cr.stroke()
        elif s.kind == ELLIPSE:
            cr.save()
            cr.translate((s.x + s.x2) / 2, (s.y + s.y2) / 2)
            cr.scale(max(abs(s.x2 - s.x) / 2, 1e-6), max(abs(s.y2 - s.y) / 2, 1e-6))
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.stroke()
        elif s.kind == LINE:
            cr.move_to(s.x, s.y)
            cr.line_to(s.x2, s.y2)
            cr.stroke()

    if selected:
        x0, y0, x1, y1 = s.bounds()
        pad = 4 * u
        cr.set_source_rgba(0.235, 0.651, 0.969, 0.95)
        cr.set_line_width(1.4 * u)
        cr.set_dash([5 * u, 4 * u], 0)
        cr.rectangle(x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad)
        cr.stroke()
        cr.set_dash([], 0)
        hs = 4 * u
        for hx, hy in ((x0 - pad, y0 - pad), (x1 + pad, y0 - pad),
                       (x0 - pad, y1 + pad), (x1 + pad, y1 + pad)):
            cr.set_source_rgba(1, 1, 1, 1)
            cr.rectangle(hx - hs, hy - hs, 2 * hs, 2 * hs)
            cr.fill()
    cr.restore()
