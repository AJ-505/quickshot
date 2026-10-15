"""Inline SVG icons for the toolbar.

Kept as 24x24 stroked paths on a transparent canvas; the toolbar recolours the
active tool with CSS rather than swapping assets.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib  # noqa: E402

_S = ('xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
      'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" '
      'stroke-linecap="round" stroke-linejoin="round"')

# Filled variant: no stroke on the root, so glyphs must not add one either.
_SF = ('xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
       'viewBox="0 0 24 24" fill="currentColor"')

ICONS: dict[str, str] = {
    "pointer": (
        f'<svg {_SF}>'
        '<path d="M5 3.2 18.6 12.1a.55.55 0 0 1-.2 1l-5.3.9a.5.5 0 0 0-.35.4l-.85 5.3a.55.55 0 0 1-1 .2Z"/>'
        "</svg>"
    ),
    "rect": f'<svg {_S}><rect x="3.5" y="5.5" width="17" height="13" rx="2"/></svg>',
    "ellipse": f'<svg {_S}><ellipse cx="12" cy="12" rx="8.5" ry="6.5"/></svg>',
    "line": f'<svg {_S}><path d="M5 19 19 5"/></svg>',
    "freehand": (
        f'<svg {_S}><path d="M3 16.5c2.5.4 3.2-6 5.5-6s1.3 5 3.4 5 2.2-8 4.3-8 1.3 6 4.8 5.5"/>'
        '<path d="M17.5 20.5H20"/></svg>'
    ),
    "text": (
        f'<svg {_S}><path d="M5 6.5V5h14v1.5M12 5v14M9 19h6"/></svg>'
    ),
    "blur": (
        f'<svg {_S}>'
        '<rect x="3.5" y="3.5" width="17" height="17" rx="2"/>'
        '<path d="M8.5 8.5h2v2h-2zM13.5 8.5h2v2h-2zM8.5 13.5h2v2h-2zM13.5 13.5h2v2h-2z"/>'
        "</svg>"
    ),
    "step": (
        f'<svg {_S}><circle cx="12" cy="12" r="8"/></svg>'
    ),
    "select": (
        f'<svg {_S}><path d="M6 3.5 18 12l-5 .8-.8 5.2Z" stroke-width="1.6"/>'
        '<path d="M6 3.5V20" stroke-dasharray="2 2.5" stroke-width="1.3"/></svg>'
    ),
    "undo": (
        f'<svg {_S}><path d="M4 9h9.5a5.5 5.5 0 0 1 0 11H8"/><path d="M7.5 5 4 9l3.5 4"/></svg>'
    ),
    "redo": (
        f'<svg {_S}><path d="M20 9h-9.5a5.5 5.5 0 0 0 0 11H16"/><path d="M16.5 5 20 9l-3.5 4"/></svg>'
    ),
    "copy": (
        f'<svg {_S}><rect x="8.5" y="3.5" width="12" height="14" rx="2"/>'
        '<path d="M15.5 20.5h-10a2 2 0 0 1-2-2v-10"/></svg>'
    ),
    "save": f'<svg {_S}><path d="M5 3.5h11L20 7.5v13H5z"/><path d="M8.5 3.5v6h7v-6M8.5 20.5v-6h7v6"/></svg>',
    "close": f'<svg {_S}><path d="M6 6l12 12M18 6 6 18"/></svg>',
    "help": (
        f'<svg {_S}><circle cx="12" cy="12" r="8.5"/>'
        '<path d="M9.6 9.4a2.5 2.5 0 1 1 3.3 2.4c-.6.2-.9.8-.9 1.4v.4"/>'
        '<path d="M12 16.8v.01" stroke-width="2.2"/></svg>'
    ),
    "blursoft": (
        f'<svg {_S}><rect x="3.5" y="3.5" width="17" height="17" rx="2"/>'
        '<path d="M7 8.5c3-1.5 7 1.5 10 0M7 13c3-1.5 7 1.5 10 0" stroke-width="1.5"/></svg>'
    ),
    "zoomin": f'<svg {_S}><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.5-4.5M11 8.5v5M8.5 11h5"/></svg>',
    "zoomout": f'<svg {_S}><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.5-4.5M8.5 11h5"/></svg>',
    "reset": f'<svg {_S}><path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5"/><path d="M4 4v4h4"/></svg>',
}

_cache: dict[tuple[str, int], Gdk.Texture] = {}


def icon(name: str, size: int = 22) -> Gdk.Texture:
    key = (name, size)
    if key in _cache:
        return _cache[key]
    svg = ICONS.get(name)
    if svg is None:
        raise KeyError(f"no icon {name!r}")
    tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(svg.encode("utf-8")))
    if size != 24:
        tex = scale_texture(tex, size)
    _cache[key] = tex
    return tex


def scale_texture(tex: Gdk.Texture, size: int) -> Gdk.Texture:
    w, h = tex.get_width(), tex.get_height()
    scale = size / max(w, h)
    return tex.scale(int(w * scale), int(h * scale),
                     0.5, 0.5, Gdk.Interpolation.BILINEAR) \
        if hasattr(tex, "scale") else tex
