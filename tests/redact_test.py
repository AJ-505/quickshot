#!/usr/bin/env python3
"""Isolate the redaction path: dump region, small, and final patch."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

import cairo
from quickshot import render
from quickshot.model import BLUR, Shape
from quickshot.render import View, ctx

W, H = 600, 200
img = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
c = ctx(img)
c.set_source_rgb(0.10, 0.11, 0.13)
c.paint()
c.set_source_rgb(0.20, 0.21, 0.25)
c.rectangle(0, 0, W, 60)
c.fill()
c.set_source_rgb(0.90, 0.55, 0.30)
c.select_font_face("Monospace", 0, 0)
c.set_font_size(22)
c.move_to(10, 40)
c.show_text("password: hunter2correcthorse")

s = Shape(kind=BLUR, x=0, y=0, x2=600, y2=60, blur_mode="mosaic", block=9.0)
patch = render.redact(img, s)
print("patch", patch.get_width(), "x", patch.get_height(), "stride", patch.get_stride())

out = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
oc = ctx(out)
oc.set_source_surface(img, 0, 0)
oc.paint()
oc.set_source_surface(patch, s.bounds()[0], s.bounds()[1])
oc.paint()
out.write_to_png("redact_mosaic.png")

sb = Shape(kind=BLUR, x=0, y=0, x2=600, y2=60, blur_mode="blur")
render.redact(img, sb).write_to_png("redact_blur_patch.png")

# How much does the patch actually differ from the source region?
a = bytes(img.get_data())
b = bytes(patch.get_data())
diff = sum(1 for x, y in zip(a, b) if abs(x - y) > 12)
print(f"bytes differing from source: {diff}/{len(a)} ({100*diff/len(a):.1f}%)")
