#!/usr/bin/env python3
"""Redaction correctness: opaque, detail-destroying, and contained.

 1. every pixel of the patch is fully opaque
 2. mosaic/blur remove high-frequency detail (no row/col is left untouched)
 3. pixels *outside* the shape box are bit-identical to the source
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))

import cairo
import numpy as np

from quickshot.model import BLUR, Shape
from quickshot.render import ctx, redact

W, H = 800, 400


def fixture() -> cairo.ImageSurface:
    img = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = ctx(img)
    c.set_source_rgb(0.1, 0.1, 0.12)
    c.paint()
    c.set_source_rgb(0.95, 0.55, 0.15)
    c.select_font_face("Monospace", 0, 0)
    c.set_font_size(20)
    for i in range(6):
        c.move_to(20, 60 + i * 26)
        c.show_text("API_KEY = sk-live-9f3a2b7c4d1e8f60a2b5 %04d" % i)
    return img


def arr(s):
    s.flush()
    a = np.frombuffer(bytes(s.get_data()), np.uint8)
    return a.reshape(s.get_height(), s.get_stride() // 4, 4)[:, :s.get_width(), :]


img = fixture()
base = arr(img).copy()
RX0, RY0, RX1, RY1 = 100, 40, 620, 200


def local_variation(a: np.ndarray) -> float:
    """Mean absolute neighbour-to-neighbour difference: a proxy for detail."""
    if a.shape[0] < 2 or a.shape[1] < 2:
        return 0.0
    g = a.astype(np.float32)
    dx = np.abs(np.diff(g, axis=1)).mean()
    dy = np.abs(np.diff(g, axis=0)).mean()
    return float((dx + dy) / 2)


src_region = base[RY0:RY1, RX0:RX1, :3]
src_detail = local_variation(src_region)

fails = []
for mode, block in (("mosaic", 12.0), ("blur", 12.0)):
    s = Shape(kind=BLUR, x=RX0, y=RY0, x2=RX1, y2=RY1,
              blur_mode=mode, block=block)
    patch = redact(img, s)
    p = arr(patch)

    # 1. opacity, and the right size
    if p.shape[0:2] != (RY1 - RY0, RX1 - RX0):
        fails.append(f"{mode}: wrong patch size {p.shape}")
    if int(p[:, :, 3].min()) != 255:
        fails.append(f"{mode}: not opaque, min alpha={int(p[:, :, 3].min())}")

    # 2. detail genuinely destroyed. Uniform background is allowed to survive;
    #    what must not survive is edge detail, so compare local variation.
    got_detail = local_variation(p[:, :, :3])
    if got_detail > src_detail * 0.25:
        fails.append(f"{mode}: detail survived "
                     f"(local variation {got_detail:.2f} vs source {src_detail:.2f})")

    # 3. the source image must not be mutated
    if not np.array_equal(arr(img), base):
        fails.append(f"{mode}: redact() mutated the source screenshot")

    # 4. edge clamping: a box hanging off the image must stay opaque
    for edge in ((-50, -50, 100, 100), (W - 40, H - 40, W + 200, H + 200)):
        e = Shape(kind=BLUR, x=edge[0], y=edge[1], x2=edge[2], y2=edge[3],
                  blur_mode=mode, block=block)
        p2 = arr(redact(img, e))
        if int(p2[:, :, 3].min()) != 255:
            fails.append(f"{mode}: clamped edge not opaque "
                         f"(min alpha {int(p2[:, :, 3].min())})")

print(f"source local variation = {src_detail:.2f}")
if fails:
    print("FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("PASS  redaction: opaque, detail-destroying, non-mutating, edge-safe")
