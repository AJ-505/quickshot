"""Annotation document model.

The whole editor state is a flat list of `Shape` values. Keeping one shape type
with a `kind` discriminator (rather than a class per tool) means rendering is a
single function and undo is a plain deep copy.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import List, Tuple

RGBA = Tuple[float, float, float, float]

# Tool identifiers, in toolbar order.
POINTER = "pointer"
RECT = "rect"
ELLIPSE = "ellipse"
LINE = "line"
FREEHAND = "freehand"
TEXT = "text"
BLUR = "blur"
STEP = "step"
SELECT = "select"

TOOLS = [POINTER, RECT, ELLIPSE, LINE, FREEHAND, TEXT, BLUR, STEP]
DRAW_TOOLS = set(TOOLS) - {SELECT}

# Palette: index 0 is the default annotation colour.
PALETTE: List[RGBA] = [
    (1.000, 0.267, 0.267, 1.0),  # red
    (1.000, 0.647, 0.043, 1.0),  # amber
    (0.310, 0.878, 0.310, 1.0),  # green
    (0.235, 0.651, 0.969, 1.0),  # blue
    (0.878, 0.243, 0.945, 1.0),  # purple
    (1.000, 1.000, 1.000, 1.0),  # white
]


@dataclass
class Shape:
    """One annotation.

    Geometry (`x`, `y`, `x2`, `y2`, `points`) is in *image pixel* space, so it
    is independent of zoom and screen scale.

    `width` and `size` are stored in *logical screen pixels at zoom 1*; the
    renderer converts them through the fit scale so a stroke keeps the same
    apparent thickness no matter how far you zoom in.
    """

    kind: str
    x: float = 0.0
    y: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    color: RGBA = PALETTE[0]
    width: float = 3.0          # stroke width, logical px
    size: float = 22.0          # text font size / step radius, logical px
    text: str = ""
    points: List[Tuple[float, float]] = field(default_factory=list)
    step: int = 0
    blur_mode: str = "mosaic"   # "mosaic" | "blur"
    block: float = 10.0         # mosaic block size, image px

    def copy(self) -> "Shape":
        return copy.deepcopy(self)

    def bounds(self) -> Tuple[float, float, float, float]:
        if self.kind == FREEHAND and self.points:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            return min(xs), min(ys), max(xs), max(ys)
        return min(self.x, self.x2), min(self.y, self.y2), max(self.x, self.x2), max(self.y, self.y2)

    def translate(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy
        self.x2 += dx
        self.y2 += dy
        if self.points:
            self.points = [(px + dx, py + dy) for px, py in self.points]


def _hit(shape: Shape, px: float, py: float, tol: float) -> bool:
    """Point hit test in image space. `tol` is already scaled to image px."""
    if shape.kind == FREEHAND:
        for (ax, ay), (bx, by) in zip(shape.points, shape.points[1:]):
            vx, vy = bx - ax, by - ay
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
            dx, dy = px - (ax + t * vx), py - (ay + t * vy)
            if dx * dx + dy * dy <= tol * tol:
                return True
        return False
    if shape.kind == BLUR:
        x0, y0, x1, y1 = shape.bounds()
        return x0 - tol <= px <= x1 + tol and y0 - tol <= py <= y1 + tol
    if shape.kind == STEP:
        cx, cy = (shape.x + shape.x2) / 2, (shape.y + shape.y2) / 2
        r = shape.size + tol
        return (px - cx) ** 2 + (py - cy) ** 2 <= r * r
    if shape.kind == TEXT:
        x0, y0, x1, y1 = shape.bounds()
        return x0 - tol <= px <= x1 + tol and y0 - tol <= py <= y1 + tol
    # Stroked geometry: distance to the segment.
    ax, ay, bx, by = shape.x, shape.y, shape.x2, shape.y2
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    dx, dy = px - (ax + t * vx), py - (ay + t * vy)
    reach = tol + shape.width / 2 + (shape.size / 2 if shape.kind == POINTER else 0.0)
    return dx * dx + dy * dy <= reach * reach


class Doc:
    """Shape list plus undo/redo.

    Undo stores deep copies of the whole list. Annotation counts here are tiny
    (tens of shapes), so this trades a little memory for dead-simple, obviously
    correct history -- including freehand, which is one entry per stroke.
    """

    def __init__(self) -> None:
        self.shapes: List[Shape] = []
        self._undo: List[List[Shape]] = []
        self._redo: List[List[Shape]] = []
        self._dirty = False  # a coalescable in-progress edit
        self.rev = 0         # bumped on every mutation, for render caching

    # -- history ---------------------------------------------------------
    def mark(self) -> None:
        """Snapshot before a mutation. Coalesces until `end_mark`."""
        if self._dirty:
            return
        self.rev += 1
        self._undo.append([s.copy() for s in self.shapes])
        if len(self._undo) > 200:
            self._undo.pop(0)
        self._redo.clear()
        self._dirty = True

    def end_mark(self) -> None:
        self._dirty = False

    def undo(self) -> bool:
        self._dirty = False
        if not self._undo:
            return False
        self.rev += 1
        self._redo.append([s.copy() for s in self.shapes])
        self.shapes = self._undo.pop()
        return True

    def redo(self) -> bool:
        self._dirty = False
        if not self._redo:
            return False
        self.rev += 1
        self._undo.append([s.copy() for s in self.shapes])
        self.shapes = self._redo.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    # -- mutation --------------------------------------------------------
    def add(self, shape: Shape, mark: bool = True) -> Shape:
        if mark:
            self.mark()
        self.shapes.append(shape)
        return shape

    def remove(self, shape: Shape) -> None:
        if shape in self.shapes:
            self.mark()
            self.shapes.remove(shape)

    def clear(self) -> None:
        if not self.shapes:
            return
        self.mark()
        self.shapes.clear()

    def next_step(self) -> int:
        used = [s.step for s in self.shapes if s.kind == STEP]
        return (max(used) + 1) if used else 1

    def renumber_steps(self) -> None:
        """Keep step numbers in left-to-right order after a move."""
        steps = [s for s in self.shapes if s.kind == STEP]
        for i, s in enumerate(sorted(steps, key=lambda s: s.x), start=1):
            s.step = i

    def pick(self, px: float, py: float, tol: float) -> Shape | None:
        """Topmost shape under a point, or None."""
        for shape in reversed(self.shapes):
            if _hit(shape, px, py, tol):
                return shape
        return None

    def pick_box(self, x0: float, y0: float, x1: float, y1: float) -> list[Shape]:
        ax, bx = sorted((x0, x1))
        ay, by = sorted((y0, y1))
        out = []
        for s in self.shapes:
            sx0, sy0, sx1, sy1 = s.bounds()
            if sx0 >= ax and sx1 <= bx and sy0 >= ay and sy1 <= by:
                out.append(s)
        return out
