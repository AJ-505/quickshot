#!/usr/bin/env python3
"""Open the editor on an existing PNG, without the service or the portal.

Usage: tools/preview.py IMAGE.png

The image is copied first, because the editor deletes its working file on close.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from quickshot.service import Quickshot  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    work = os.path.join(tempfile.mkdtemp(prefix="qs-preview-"), "shot.png")
    shutil.copyfile(sys.argv[1], work)
    app = Quickshot()

    def on_startup(*_a) -> None:
        app._open_editor()
        app.editor.load(work)
        app.gtk_app.hold()

    app.on_editor_closed = app.gtk_app.quit
    app.gtk_app.connect("startup", on_startup)
    app.gtk_app.run([])
    return 0


if __name__ == "__main__":
    sys.exit(main())
