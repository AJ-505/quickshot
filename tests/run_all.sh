#!/usr/bin/env bash
# Run the Quickshot test suite. Each test is independent; failures are reported
# per test so one failure does not hide the rest.
#
# --ci runs only the tests that need a display but not a real GNOME Wayland
# session (see tests/run_ci.sh). Without it the session-only tests run as well.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.."

CI_TESTS=(
  "tests/icon_verify.py"
  "tests/redact_verify.py"
  "tests/keymap_test.py"
  "tests/stale_state_test.py"
  "tests/show_test.py"
  "tests/gui_smoke.py"
  "tests/e2e_test.py"
  "tests/latency_test.py"
)

SESSION_TESTS=(
  "tests/clipboard_verify.py"
)

TESTS=("${CI_TESTS[@]}")
if [ "${1:-}" != "--ci" ]; then
  TESTS+=("${SESSION_TESTS[@]}")
fi

pass=0
fail=0
for t in "${TESTS[@]}"; do
  printf '%-32s ' "$(basename "$t")"
  out=$(timeout 90 python3 "$t" 2>&1 | grep -vE "GLib-GIO-WARNING|^\(python[0-9]")
  if [ $? -eq 0 ] || printf '%s' "$out" | grep -qE "^(PASS|INCONCLUSIVE)"; then
    note=$(printf '%s' "$out" | grep -E "^(PASS|INCONCLUSIVE)" | head -1)
    printf 'ok    %s\n' "$note"
    pass=$((pass + 1))
  else
    printf 'FAIL\n'
    printf '%s\n' "$out" | sed 's/^/    /'
    fail=$((fail + 1))
  fi
done

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
