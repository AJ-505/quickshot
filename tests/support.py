"""Shared fixtures for the tests: an isolated runtime dir and a PNG maker.

Import this before `quickshot` so the control socket and the capture cache
land in a throwaway directory and never touch the owner's live service.
"""
import atexit
import os
import shutil
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

SANDBOX = tempfile.mkdtemp(prefix="qs-test-")
atexit.register(shutil.rmtree, SANDBOX, True)

RUNTIME = os.path.join(SANDBOX, "run")
CACHE = os.path.join(SANDBOX, "cache")
os.makedirs(RUNTIME, mode=0o700)
os.makedirs(CACHE)

os.environ["XDG_RUNTIME_DIR"] = RUNTIME
os.environ["XDG_CACHE_HOME"] = CACHE
os.environ["QUICKSHOT_NO_SPAWN"] = "1"

import cairo  # noqa: E402


def make_png(name: str, w: int = 800, h: int = 500) -> str:
    from quickshot.render import ctx
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    c = ctx(s)
    c.set_source_rgb(0.12, 0.13, 0.16)
    c.paint()
    c.set_source_rgb(0.85, 0.86, 0.9)
    c.select_font_face("Monospace", 0, 0)
    c.set_font_size(18)
    for i in range(max(1, min(10, h // 40))):
        c.move_to(30, 40 + i * 30)
        c.show_text(f"captured line {i}")
    path = os.path.join(SANDBOX, name)
    s.write_to_png(path)
    return path
