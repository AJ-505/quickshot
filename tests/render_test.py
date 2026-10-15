#!/usr/bin/env python3
"""Render every annotation kind onto a synthetic 'screenshot' and save a PNG.

This is a pure-render test: no display needed, so it proves the model -> cairo
path works and gives something to look at.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

import cairo  # noqa: E402
from quickshot import render
from quickshot.render import ctx  # noqa: E402
from quickshot.model import (BLUR, ELLIPSE, FREEHAND, LINE, PALETTE, POINTER,  # noqa: E402
                             RECT, STEP, TEXT, Doc, Shape)
from quickshot.render import View  # noqa: E402

W, H = 1200, 700

# --- build a fake screenshot: a window with text, a "secret", a chart ------
img = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
c = ctx(img)
c.set_source_rgb(0.10, 0.11, 0.13)
c.paint()
# title bar
c.set_source_rgb(0.16, 0.17, 0.20)
c.rectangle(0, 0, W, 46)
c.fill()
c.set_source_rgb(0.95, 0.30, 0.30)
c.arc(24, 23, 7, 0, 6.284)
c.fill()
c.set_source_rgb(0.95, 0.70, 0.25)
c.arc(46, 23, 7, 0, 6.284)
c.fill()
c.set_source_rgb(0.35, 0.80, 0.45)
c.arc(68, 23, 7, 0, 6.284)
c.fill()
# some code-ish text
c.set_source_rgb(0.80, 0.83, 0.88)
c.select_font_face("Monospace", 0, 0)
c.set_font_size(15)
for i, line in enumerate([
    "def connect(host, port):",
    "    sock = socket.socket(socket.AF_INET)",
    "    sock.settimeout(30)",
    "    sock.connect((host, port))",
    "    return sock",
    "",
    "API_KEY = 'sk-live-9f3a2b7c4d1e8f60a2b5'",
]):
    c.move_to(30, 90 + i * 24)
    c.show_text(line)
# a "secret" blob to redact
c.set_source_rgb(0.20, 0.21, 0.25)
c.rectangle(640, 70, 520, 70)
c.fill()
c.set_source_rgb(0.90, 0.55, 0.30)
c.select_font_face("Monospace", 0, 0)
c.set_font_size(20)
c.move_to(660, 113)
c.show_text("password: hunter2correcthorse")
# a chart
c.set_source_rgb(0.20, 0.21, 0.25)
c.rectangle(640, 170, 520, 260)
c.fill()
import math
pts = [(660, 400), (740, 350), (820, 372), (900, 280), (980, 310), (1060, 225)]
c.set_source_rgb(0.30, 0.60, 0.95)
c.set_line_width(3)
for i in range(len(pts) - 1):
    c.move_to(*pts[i])
    c.line_to(*pts[i + 1])
c.stroke()
for p in pts:
    c.arc(p[0], p[1], 5, 0, 6.284)
    c.fill()

# --- annotations -----------------------------------------------------------
doc = Doc()
doc.add(Shape(kind=POINTER, x=760, y=250, x2=905, y2=284,
              color=PALETTE[0], width=5.0), mark=False)
doc.add(Shape(kind=RECT, x=625, y=55, width=4.0, color=PALETTE[3],
              x2=1175, y2=155), mark=False)
doc.add(Shape(kind=ELLIPSE, x=800, y=260, width=4.0, color=PALETTE[2],
              x2=900, y2=300), mark=False)
doc.add(Shape(kind=LINE, x=30, y=520, x2=560, y2=560, width=4.0,
              color=PALETTE[1]), mark=False)
doc.add(Shape(kind=FREEHAND, width=4.0, color=PALETTE[4], points=[
    (60, 600), (110, 575), (150, 640), (200, 570), (250, 620),
    (300, 580), (350, 630), (400, 590),
]), mark=False)
doc.add(Shape(kind=BLUR, x=650, y=78, x2=1155, y2=130, blur_mode="mosaic",
              block=9.0), mark=False)
doc.add(Shape(kind=BLUR, x=655, y=190, x2=900, y2=250, blur_mode="blur"), mark=False)
doc.add(Shape(kind=TEXT, x=60, y=470, size=34.0, color=PALETTE[5],
              text="watch this line"), mark=False)
doc.add(Shape(kind=STEP, x=30, y=230, x2=30, y2=230, step=1,
              color=PALETTE[0], size=26.0), mark=False)
doc.add(Shape(kind=STEP, x=90, y=230, x2=90, y2=230, step=2,
              color=PALETTE[0], size=26.0), mark=False)
# a plain mouse-pointer glyph (tap, not drag)
doc.add(Shape(kind=POINTER, x=200, y=560, x2=200, y2=560, size=24.0,
              color=PALETTE[5]), mark=False)

view = View(scale=1.0, fit=1.0, ox=0.0, oy=0.0, zoom=1.0)
out = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
oc = ctx(out)
oc.set_source_surface(img, 0, 0)
oc.paint()
for s in doc.shapes:
    render.draw_shape(oc, img, s, view)

dest = sys.argv[1] if len(sys.argv) > 1 else "render_test.png"
out.write_to_png(dest)
print(f"wrote {dest}  shapes={len(doc.shapes)}  rev={doc.rev}")
