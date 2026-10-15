"""GNOME keybinding management for Quickshot.

PrintScreen currently triggers GNOME's own `show-screenshot-ui`. To route it
through Quickshot we clear that binding and add a custom media-keys binding for
the same physical key. The original values are recorded so `uninstall` can put
everything back exactly.

Existing custom bindings are appended to, never replaced.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

SHELL_SCHEMA = "org.gnome.shell.keybindings"
SHELL_KEY = "show-screenshot-ui"
MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"

# Every key Quickshot answers to. Print is deliberately NOT here: it stays on
# GNOME's own screenshot UI so there is always one key that does the plain,
# no-editor thing. Add "Print" to this list to claim it as well.
DEFAULT_BINDINGS = ["<Super><Shift>s"]
STATE_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "quickshot"
)
STATE_FILE = os.path.join(STATE_DIR, "keybinding-backup.json")


def _g(*args: str) -> str:
    r = subprocess.run(["gsettings", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gsettings {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def _parse_list(s: str) -> list[str]:
    """Parse gsettings' `@as [...]` output into a Python list."""
    s = s.strip()
    if s.startswith("@as"):
        s = s[s.index("[") + 1:s.rindex("]")]
    out, cur, quote, esc = [], "", False, False
    for ch in s:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "'":
            quote = not quote
            if not quote:
                out.append(cur)
                cur = ""
        elif quote:
            cur += ch
    return out


def launcher_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".local", "bin", "quickshot")


def _current_customs() -> list[str]:
    return _parse_list(_g("get", MEDIA_SCHEMA, "custom-keybindings"))


def owned_paths() -> list[str]:
    """Custom-keybinding paths that belong to Quickshot."""
    return [p for p in _current_customs() if p.rstrip("/").endswith("/quickshot")
            or "/quickshot-" in p]


def status() -> dict:
    customs = _current_customs()
    return {
        "shell_show_screenshot_ui": _parse_list(_g("get", SHELL_SCHEMA, SHELL_KEY)),
        "custom_keybindings": customs,
        "quickshot": {p: _dconf_read(f"{p.rstrip(chr(47))}/binding") for p in owned_paths()},
    }


def install(bindings: list[str] | None = None, launcher: str | None = None) -> None:
    bindings = bindings or DEFAULT_BINDINGS
    launcher = launcher or launcher_path()
    if not os.path.exists(launcher):
        raise SystemExit(f"launcher not found: {launcher}")

    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as fh:
            json.dump({
                "shell_show_screenshot_ui": _parse_list(_g("get", SHELL_SCHEMA, SHELL_KEY)),
                "bindings": bindings,
            }, fh, indent=2)

    # 1. take Print away from the shell only if we are claiming it
    if any(_is_print(b) for b in bindings):
        _set_validated(SHELL_SCHEMA, SHELL_KEY, "as", "[]")
    else:
        # Print is not ours: hand the native screenshot UI back to GNOME.
        saved = ["Print"]
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as fh:
                saved = json.load(fh).get("shell_show_screenshot_ui") or ["Print"]
        if _parse_list(_g("get", SHELL_SCHEMA, SHELL_KEY)) != saved:
            _set_validated(SHELL_SCHEMA, SHELL_KEY, "as", _gvariant_list(saved))

    # 2. drop any binding we registered previously, then add the current set,
    #    leaving every other custom binding alone.
    #
    #    The trailing slash is mandatory. gsd-media-keys builds each child key
    #    path by concatenating the array entry with "name"/"command"/"binding".
    #    Without the slash it looks up ".../quickshotname", gets NULL, and
    #    dereferences it: "g_variant_get_string: assertion 'value != NULL'
    #    failed" followed by SIGSEGV, which kills every custom shortcut on the
    #    machine. Every entry GNOME itself writes has the slash.
    keep = [c for c in _current_customs() if c not in owned_paths()]
    wanted = [f"{CUSTOM_BASE}/quickshot/" if i == 0
              else f"{CUSTOM_BASE}/quickshot-{i}/" for i in range(len(bindings))]
    _set_validated(MEDIA_SCHEMA, "custom-keybindings", "as",
                   _gvariant_list(keep + wanted))

    # 3. the per-binding leaf keys. These are not addressable through GSettings
    #    on this system: `org.gnome.settings-daemon.plugins.media-keys` is not
    #    relocatable and no child schema is exposed, so `gsettings set` fails
    #    with "No such schema" or "not relocatable". They live in the same dconf
    #    database, which is what gnome-settings-daemon actually reads, so write
    #    them there -- verified against an existing working custom binding.
    for i, (path, binding) in enumerate(zip(wanted, bindings)):
        label = "Quickshot" if i == 0 else f"Quickshot ({binding})"
        for key, value in (("name", label), ("command", launcher),
                           ("binding", binding)):
            _dconf_set(f"{path}{key}", _validated("s", _gvariant_str(value)))


def _is_print(binding: str) -> bool:
    return binding.replace(" ", "").lower() in ("print", "<print>")


def _dconf(key: str, action: str, value: str | None = None) -> str:
    cmd = ["dconf", action, key] + ([value] if value is not None else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"dconf {action} {key}: {r.stderr.strip()}")
    return r.stdout.strip()


def _dconf_set(key: str, gvariant: str) -> None:
    _dconf(key, "write", gvariant)


def _dconf_read(key: str) -> str:
    try:
        return _dconf(key, "read")
    except RuntimeError:
        return "<unset>"


def _dconf_reset(key: str) -> None:
    # 'reset' takes no value; tolerate either spelling of the subcommand
    try:
        _dconf(key, "reset")
    except RuntimeError:
        subprocess.run(["dconf", "reset", "-f", key], capture_output=True)


def _gvariant_str(value: str) -> str:
    """Quote a string as GVariant text format."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _gvariant_list(values: list[str]) -> str:
    return "[" + ", ".join(_gvariant_str(v) for v in values) + "]"


def _validated(vtype: str, text: str) -> str:
    """Refuse to hand GSettings a value we have not parsed first.

    An early version of this file applied shell quoting to the GVariant text.
    The result was syntactically invalid, and gsd-media-keys *segfaulted*
    parsing it, which silently killed every custom keyboard shortcut on the
    machine until the service was restarted. Never write unvalidated GVariant.
    """
    from gi.repository import GLib
    try:
        GLib.Variant.parse(GLib.VariantType.new(vtype), text, None, None)
    except Exception as exc:
        raise RuntimeError(f"refusing to write invalid GVariant {text!r}: {exc}")
    return text


def _set_validated(schema: str, key: str, vtype: str, text: str) -> None:
    _g("set", schema, key, _validated(vtype, text))


def uninstall() -> None:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as fh:
            saved = json.load(fh)
        _set_validated(SHELL_SCHEMA, SHELL_KEY, "as",
                       _gvariant_list(saved["shell_show_screenshot_ui"]))
    ours = owned_paths()
    for path in ours:
        for key in ("name", "command", "binding"):
            try:
                _dconf_reset(f"{path.rstrip(chr(47))}/{key}")
            except Exception:
                pass
    keep = [c for c in _current_customs() if c not in ours]
    _set_validated(MEDIA_SCHEMA, "custom-keybindings", "as", _gvariant_list(keep))
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "install":
        bindings = argv[2:] or DEFAULT_BINDINGS
        install(bindings)
        print("routed to Quickshot: " + ", ".join(bindings))
    elif cmd == "uninstall":
        uninstall()
        print("Print restored to the GNOME screenshot UI")
    elif cmd == "status":
        print(json.dumps(status(), indent=2))
    else:
        print(f"usage: {argv[0]} [install [BINDING ...]|uninstall|status]")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
