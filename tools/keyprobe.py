#!/usr/bin/env python3
"""Report what keys your keyboard actually delivers to Linux.

Run it, then press the key combination you are curious about. It prints every
keycode it sees, at two levels:

  evdev  - raw kernel events. The only place a key can show up if the desktop
           is swallowing it.
  xkb    - what GNOME/GTK would see, i.e. what a keybinding could match.

A key that is handled by the laptop's firmware never appears in either, which
is the usual reason a "Fn + something" shortcut cannot be bound.

  python3 tools/keyprobe.py            # 20 seconds
  python3 tools/keyprobe.py --evdev    # raw events only, no GUI needed
"""
from __future__ import annotations

import argparse
import glob
import os
import struct
import sys
import time

# keycode -> name, enough to recognise the interesting ones
NAMES = {
    1: "ESC", 9: "ESC", 10: "0", 11: "1", 12: "2", 13: "3", 14: "4",
    15: "5", 16: "6", 17: "7", 18: "8", 19: "9", 28: "ENTER", 42: "LSHIFT",
    54: "RSHIFT", 56: "LALT", 100: "RALT", 97: "LCTRL", 99: "RCTRL",
    125: "KP_ENTER", 57: "SPACE", 104: "PAUSE", 183: "FN", 464: "KEY_FN",
    186: "KEY_COMPOSE", 127: "KP_MUTE", 113: "MUTE", 172: "KP_VOLUMEDOWN",
    174: "KP_VOLUMEUP", 121: "XF86AudioMute", 122: "XF86AudioLowerVolume",
    123: "XF86AudioRaiseVolume", 110: "KEY_SYSRQ", 119: "KEY_PAUSE",
    129: "KEY_HOMEPAGE", 130: "KEY_UP", 131: "KEY_PAGEUP", 132: "KEY_LEFT",
    133: "KEY_RIGHT", 134: "KEY_END", 135: "KEY_DOWN", 136: "KEY_PAGEDOWN",
    137: "KEY_INSERT", 138: "KEY_DELETE", 140: "KEY_KP7", 111: "KEY_KP7",
    140 + 0: "", 163: "KEY_BRIGHTNESSDOWN", 172 + 0: "",
    84: "KEY_ZOOMIN", 85: "KEY_ZOOMOUT", 125 + 0: "",
    202: "KEY_PROG1", 203: "KEY_PROG2", 217: "KEY_FN_RIGHT_SHIFT",
    464 + 0: "", 465: "KEY_FN_ESC", 518: "KEY_CONFIG",
}
for _i in range(1, 25):
    NAMES.setdefault(59 + _i, f"F{_i}")


def keyname(code: int) -> str:
    if code in NAMES:
        return NAMES[code]
    if 59 <= code <= 87:
        return f"F{code - 58}"
    if 88 <= code <= 107:
        return f"F{code - 88 + 1}"
    return f"keycode-{code}"


def watch_evdev(seconds: float) -> None:
    """Print raw kernel key events. Catches keys the desktop hides."""
    fd = os.open("/dev/input/event0", os.O_RDONLY)
    fmt = "llHHi"  # time sec, usec, type, code, value
    size = struct.calcsize(fmt)
    print("evdev: watching /dev/input/event0 "
          f"({seconds:.0f}s). Press the key now.")
    print("  type 1 = EV_KEY   (1=down, 0=up, 2=repeat)\n")
    end = time.time() + seconds
    while time.time() < end:
        try:
            data = os.read(fd, size * 40)
        except OSError:
            break
        if not data:
            time.sleep(0.01)
            continue
        for off in range(0, len(data) - size + 1, size):
            _s, _us, etype, code, value = struct.unpack_from(fmt, data, off)
            if etype == 1:
                state = {1: "DOWN", 0: "UP", 2: "repeat"}.get(value, str(value))
                print(f"  evdev  {keyname(code):24s} ({code:3d})  {state}")
    os.close(fd)


def watch_gtk(seconds: float) -> None:
    """Print what GNOME/GTK sees, i.e. what a keybinding could match."""
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk

    app = Gtk.Application(application_id="dev.quickshot.keyprobe")
    seen = {"n": 0}

    def on_key(_c, keyval, _code, state) -> bool:
        name = Gdk.keyval_name(keyval) or f"0x{keyval:x}"
        mods = []
        for bit, label in ((Gdk.ModifierType.SHIFT_MASK, "Shift"),
                           (Gdk.ModifierType.CONTROL_MASK, "Ctrl"),
                           (Gdk.ModifierType.ALT_MASK, "Alt"),
                           (Gdk.ModifierType.SUPER_MASK, "Super"),
                           (Gdk.ModifierType.HYPER_MASK, "Hyper"),
                           (Gdk.ModifierType.MOD2_MASK, "Mod2")):
            if state & bit:
                mods.append(label)
        print(f"  xkb    {name:24s}  mods={','.join(mods) or '-'}")
        seen["n"] += 1
        return True

    def on_startup(_a):
        w = Gtk.Window(application=app, title="keyprobe")
        w.set_default_size(420, 90)
        lbl = Gtk.Label(label="Press the key you want to test.\nClose this window to finish.")
        w.set_child(lbl)
        ctl = Gtk.EventControllerKey()
        ctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        ctl.connect("key-pressed", on_key)
        w.add_controller(ctl)
        w.present()

    def finish():
        print(f"\nGTK saw {seen['n']} key press(es).")
        app.quit()
        return GLib.SOURCE_REMOVE

    app.connect("startup", on_startup)
    app.connect("activate", lambda _a: app.hold())
    GLib.timeout_add_seconds(int(seconds) + 2, lambda: (app.quit(), GLib.SOURCE_REMOVE)[1])
    GLib.timeout_add_seconds(int(seconds), finish)
    app.run([])
    if seen["n"] == 0:
        print("Nothing reached GTK. If the key is firmware-handled, it will "
              "not appear here either.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evdev", action="store_true",
                    help="raw kernel events only, no window")
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    if not glob.glob("/dev/input/event*"):
        print("no /dev/input/event* nodes: cannot read raw key events")
        return 1
    if args.evdev:
        watch_evdev(args.seconds)
    else:
        watch_gtk(args.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
