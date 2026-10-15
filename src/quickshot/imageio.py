"""Image surface <-> GdkTexture plumbing (clipboard, PNG saving)."""
from __future__ import annotations

import os
import time

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib  # noqa: E402


def load_png(path: str) -> cairo.ImageSurface:
    """Decode a PNG. pycairo raises `cairo.Error` for malformed input."""
    try:
        surf = cairo.ImageSurface.create_from_png(path)
    except cairo.Error as exc:
        raise RuntimeError(f"could not decode {os.path.basename(path)}: {exc}") from exc
    if surf.get_width() < 1 or surf.get_height() < 1:
        raise RuntimeError(f"{os.path.basename(path)} decoded to an empty image")
    return surf


def to_texture(surf: cairo.ImageSurface) -> Gdk.Texture:
    """Cairo ARGB32 is premultiplied, which matches GDK's preferred upload format."""
    w, h = surf.get_width(), surf.get_height()
    stride = surf.get_stride()
    # cairo data is mutable and tied to the surface lifetime; copy it.
    data = bytes(surf.get_data())
    if stride != w * 4:
        rows = [data[i * stride:(i + 1) * stride] for i in range(h)]
        data = b"".join(r[: w * 4].ljust(w * 4, b"\0") for r in rows)
    return Gdk.MemoryTexture.new(
        w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, GLib.Bytes.new(data), w * 4
    )


def _png_bytes(surf: cairo.ImageSurface) -> GLib.Bytes:
    return to_texture(surf).save_to_png_bytes()


def _copy_via_gdk(png: GLib.Bytes) -> None:
    display = Gdk.Display.get_default()
    if display is None:
        raise RuntimeError("no display")
    # `gdk_clipboard_set_texture` is not introspected in this GDK, and
    # ContentProvider.new_for_value yields an empty format set because
    # GdkTexture is not a serialisable GType, so hand GDK encoded PNG bytes.
    display.get_clipboard().set_content(
        Gdk.ContentProvider.new_for_bytes("image/png", png)
    )


def _copy_via_wl_copy(png: GLib.Bytes) -> None:
    """Hand the PNG to wl-clipboard, which owns the selection independently.

    Verified working where Gdk's own clipboard was not: on the GNOME/Wayland
    session this was built against, Gdk reported an empty format set and
    "No compatible transfer format found" even for plain text, while wl-paste
    showed a different owner. wl-copy is the dependable path on Wayland.
    """
    import subprocess
    proc = subprocess.run(
        ["wl-copy", "--type", "image/png"],
        input=png.get_data(), capture_output=True, timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"wl-copy failed ({proc.returncode}): {proc.stderr.decode(errors='replace').strip()}"
        )


def copy_to_clipboard(surf: cairo.ImageSurface) -> None:
    """Put the annotated image on the clipboard as image/png.

    Prefers wl-copy and falls back to Gdk, so a missing wl-clipboard is not
    fatal. The Gdk attempt is skipped when it is known-broken via
    QUICKSHOT_CLIPBOARD=gdk|wl-copy.
    """
    png = _png_bytes(surf)
    prefer = os.environ.get("QUICKSHOT_CLIPBOARD", "wl-copy").lower()
    order = [_copy_via_wl_copy, _copy_via_gdk] if prefer == "wl-copy" \
        else [_copy_via_gdk, _copy_via_wl_copy]
    errors = []
    for fn in order:
        try:
            fn(png)
            return
        except FileNotFoundError as exc:
            errors.append(f"{fn.__name__}: {exc}")
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def save_png(surf: cairo.ImageSurface, directory: str, base: str = "Screenshot") -> str:
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H-%M-%S")
    path = os.path.join(directory, f"{base} from {stamp}.png")
    n = 1
    while os.path.exists(path):
        path = os.path.join(directory, f"{base} from {stamp} ({n}).png")
        n += 1
    try:
        surf.write_to_png(path)
    except cairo.Error as exc:
        raise RuntimeError(f"failed to write {path}: {exc}") from exc
    return path
