#!/usr/bin/env python3
"""Catch a flash: sample screen luminance across the capture -> editor handoff.

Grabs frames as fast as the portal allows and reports mean luminance for each,
so a one-frame white flash shows up as a spike instead of being something you
have to notice by eye. Optionally saves the frames.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"


def grab(out_path: str) -> str:
    """One non-interactive full-screen capture. Blocks until the portal replies."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    result = {}

    def on_response(*a):
        code, results = a[5].unpack()
        for k, v in results.items():
            if k == "uri":
                uri = v.unpack() if hasattr(v, 'unpack') else v
        if code == 0 and uri:
            Gio.File.new_for_uri(uri).copy(
                Gio.File.new_for_path(out_path),
                Gio.FileCopyFlags.OVERWRITE, None, None, None)
            result["ok"] = True
        GLib.MainLoop().quit()
        return None

    opts = {"interactive": GLib.Variant.new_boolean(False),
            "handle_token": GLib.Variant.new_string(f"fl{int(time.time()*1000)%100000}")}
    reply = bus.call_sync(BUS, PATH, "org.freedesktop.portal.Screenshot", "Screenshot",
                          GLib.Variant("(sa{sv})", ("", opts)),
                          GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, 20000, None)
    bus.signal_subscribe(BUS, "org.freedesktop.portal.Request", "Response",
                         reply.unpack()[0], None, Gio.DBusSignalFlags.NONE, on_response)
    GLib.timeout_add_seconds(20, lambda: GLib.MainLoop().quit())
    GLib.MainLoop().run()
    return out_path if result.get("ok") else ""


def mean_luma(path: str) -> float | None:
    if not path or not os.path.exists(path):
        return None
    try:
        surf = __import__("cairo").ImageSurface.create_from_png(path)
    except Exception:
        return None
    surf.flush()
    data = bytes(surf.get_data())
    stride = surf.get_stride()
    w, h = surf.get_width(), surf.get_height()
    # BGRA premultiplied; sample a grid for speed
    total = 0.0
    n = 0
    step_y = max(1, h // 120)
    step_x = max(1, w // 120)
    for y in range(0, h, step_y):
        base = y * stride
        for x in range(0, w, step_x):
            o = base + x * 4
            b, g, r = data[o], data[o + 1], data[o + 2]
            total += 0.2126 * r + 0.7152 * g + 0.0722 * b
            n += 1
    return round(total / max(n, 1), 1)


def main() -> int:
    save_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    print("baseline grab (editor not shown)")
    p = grab(os.path.join(save_dir, "f00_baseline.png") if save_dir else "/tmp/qs_f00.png")
    print(f"  mean luma {mean_luma(p)}")

    print("triggering quickshot ...")
    os.system(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "quickshot"))

    rows = []
    t0 = time.monotonic()
    for i in range(1, 9):
        out = os.path.join(save_dir, f"f{i:02d}.png") if save_dir else f"/tmp/qs_f{i:02d}.png"
        p = grab(out)
        dt = (time.monotonic() - t0) * 1000
        l = mean_luma(p)
        rows.append((i, round(dt), l))
        print(f"  frame {i}: t+{dt:5.0f} ms   mean luma {l}")

    vals = [r[2] for r in rows if r[2] is not None]
    if vals:
        lo, hi = min(vals), max(vals)
        print(f"\nrange {lo} .. {hi}  (spread {round(hi - lo, 1)})")
        if hi - lo > 60:
            print("FLASH DETECTED: a frame is far brighter than its neighbours.")
            return 1
    print("no brightness spike across the handoff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
