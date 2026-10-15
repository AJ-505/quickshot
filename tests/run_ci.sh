#!/usr/bin/env bash
# CI-safe subset: needs a display (e.g. `GDK_BACKEND=x11 xvfb-run -a tests/run_ci.sh`)
# but no GNOME Wayland session, wl-paste or portal.
exec "$(dirname "${BASH_SOURCE[0]}")/run_all.sh" --ci
