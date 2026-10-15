#!/usr/bin/env python3
"""Measure hotkey -> editor-visible latency with the service in its own process.

This is the production shape: a separate resident daemon, woken over the unix
socket, with a fullscreen window presented. Reports the distribution rather
than a single sample, because the whole promise is that this feels instant.
"""
import os
import statistics
import subprocess
import sys
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import cairo  # noqa: E402
import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from quickshot.render import ctx  # noqa: E402
from quickshot.service import socket_path  # noqa: E402

N = 12


def make(path, w, h):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    c = ctx(s)
    c.set_source_rgb(0.1, 0.12, 0.15)
    c.paint()
    c.set_source_rgb(0.7, 0.75, 0.85)
    c.select_font_face("Monospace", 0, 0)
    c.set_font_size(16)
    for i in range(h // 24):
        c.move_to(20, 40 + i * 24)
        c.show_text(f"row {i}")
    s.write_to_png(path)
    return path


def main():
    tmpd = tempfile.mkdtemp(prefix="qs-lat-")
    small = make(os.path.join(tmpd, "s.png"), 1280, 800)
    big = make(os.path.join(tmpd, "b.png"), 3840, 2160)

    daemon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "quickshotd")
    env = dict(os.environ, QUICKSHOT_TEST_IMAGE=big)
    proc = subprocess.Popen([daemon], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not os.path.exists(socket_path()):
            time.sleep(0.1)
        if not os.path.exists(socket_path()):
            print("FAIL: daemon never created its socket")
            return 1
        time.sleep(1.0)  # let it settle

        launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "quickshot")
        samples = []
        for i in range(N):
            t0 = time.perf_counter()
            r = subprocess.run([launcher], capture_output=True, timeout=10)
            samples.append((time.perf_counter() - t0) * 1000)
            # the editor is up and modal; close it so the next trigger is accepted
            subprocess.run([launcher], capture_output=True, timeout=10)
            time.sleep(0.35)
            if r.returncode != 0:
                print(f"FAIL: launcher exit {r.returncode}: {r.stderr.decode()[:200]}")
                return 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    samples.sort()
    print(f"hotkey -> launcher exit, {N} samples (4K capture, fullscreen window)")
    print(f"  min    {samples[0]:6.1f} ms")
    print(f"  median {statistics.median(samples):6.1f} ms")
    print(f"  p90    {samples[int(len(samples) * 0.9) - 1]:6.1f} ms")
    print(f"  max    {samples[-1]:6.1f} ms")
    if statistics.median(samples) > 250:
        print("FAIL: median wake-up is too slow to feel instant")
        return 1
    print("PASS  wake-up is instant enough to feel like a native screenshot key")
    return 0


if __name__ == "__main__":
    sys.exit(main())
