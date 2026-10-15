# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses semantic versioning.

## [0.1.0] - 2026-10-15

### Added

- Quickshot Focus, a small GNOME Shell extension that raises the editor above the window you were using.
- Mouse cursor glyph is its own tool (`M`).
- Toolbar shows each shortcut key and the current stroke width.
- `tools/preview.py` and `tools/snap_editor.py` for working on the editor without the portal.
- CI: ruff and a headless test subset.

### Changed

- The arrow tool has an arrow icon. Select has a move icon. Numbered steps show a number.
- Strokes are bolder and have a dark outline, so they read on light and dark captures.
- Text is typed in place at the click point.
- Redaction no longer draws an outline into the copied image.
- The shortcut panel is an aligned cheat sheet.

### Fixed

- The editor now opens the moment the capture finishes. Before, it waited about 100 seconds.
- Arrows draw their shaft in the chosen colour.
- Numbered steps centre their number.
- Captures display at native pixels on fractionally scaled monitors, so they are sharp.
