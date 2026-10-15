#!/usr/bin/env python3
"""Hotkey to editor-visible latency through the real daemon path.

A fresh `bin/quickshotd` runs in its own process on an isolated socket, with
QUICKSHOT_TEST_IMAGE standing in for the portal capture. The real
`bin/quickshot` launcher fires the trigger, then the daemon's status probe is
polled until it reports a visible editor holding the image. Prints the
measured latency, and fails if the editor takes longer than the bound, which
is what the 100 s deferred-show bug would have tripped.
"""
import os
import socket
import statistics
import subprocess
import sys
import time

import support  # noqa: F401, E402 (must come first)

from quickshot.service import socket_path  # noqa: E402

BOUND_MS = 1500
SIZES = [("1280x800", 1280, 800), ("4K", 3840, 2160)]
ROUNDS = 3


def status() -> str:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(socket_path())
        s.sendall(b"s")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode(errors="replace")
    except OSError:
        return ""
    finally:
        s.close()


def wait_for(pred, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.002)
    return False


def sample(image: str) -> float | None:
    daemon = os.path.join(support.ROOT, "bin", "quickshotd")
    launcher = os.path.join(support.ROOT, "bin", "quickshot")
    env = dict(os.environ, QUICKSHOT_TEST_IMAGE=image)
    proc = subprocess.Popen([daemon], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for(lambda: "visible=False" in status(), 20):
            print("  daemon never became ready")
            return None
        t0 = time.perf_counter()
        r = subprocess.run([launcher], capture_output=True, timeout=10)
        if r.returncode != 0:
            print(f"  launcher exit {r.returncode}: {r.stderr.decode()[:200]}")
            return None
        ok = wait_for(lambda: "visible=True has_image=yes" in status(), BOUND_MS / 1000 * 4)
        return (time.perf_counter() - t0) * 1000 if ok else None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    failed = False
    for label, w, h in SIZES:
        samples = []
        for i in range(ROUNDS):
            ms = sample(support.make_png(f"{label}-{i}.png", w, h))
            if ms is None:
                print(f"FAIL: {label} editor never became visible with its image")
                return 1
            samples.append(ms)
        print(f"hotkey -> editor visible, {label}, {ROUNDS} fresh daemons: "
              f"min {min(samples):.0f} ms  median {statistics.median(samples):.0f} ms  "
              f"max {max(samples):.0f} ms")
        if max(samples) > BOUND_MS:
            print(f"FAIL: {label} max {max(samples):.0f} ms exceeds {BOUND_MS} ms")
            failed = True
    if failed:
        return 1
    print(f"PASS  hotkey to visible editor stays under {BOUND_MS} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
