#!/bin/bash
# idle_watchdog.sh: shut the burst instance down after IDLE_MINUTES minutes in which nothing ran (brief 33).
# Busy means any of: a Vivado process (exact process name, so this script never matches itself), a batch in progress
# (/run/fda-busy, written by run_batch_remote.sh), or a logged-in SSH session. The first check waits 10 minutes after
# boot so the owner has time to sync. FDA_WATCHDOG_ONCE=1 runs one check and prints the decision (tests).
IDLE_MINUTES="${IDLE_MINUTES:-20}"
STATE="${FDA_WATCHDOG_STATE:-/run/fda-idle-since}"
busy() {
  pgrep -x vivado >/dev/null 2>&1 && return 0
  [ -e "${FDA_BUSY_FILE:-/run/fda-busy}" ] && return 0
  [ -n "$(who 2>/dev/null)" ] && return 0
  return 1
}
check() {
  local now since
  now=$(date +%s)
  if busy; then rm -f "$STATE"; echo busy; return; fi
  [ -f "$STATE" ] || echo "$now" >"$STATE"
  since=$(cat "$STATE")
  if [ $(( (now - since) / 60 )) -ge "$IDLE_MINUTES" ]; then
    echo "idle for $(( (now - since) / 60 )) min: shutting down"
    [ "${FDA_WATCHDOG_ONCE:-0}" = 1 ] || shutdown -h now "fda burst: idle"
  else
    echo "idle for $(( (now - since) / 60 )) min"
  fi
}
if [ "${FDA_WATCHDOG_ONCE:-0}" = 1 ]; then check; exit 0; fi
sleep 600
while true; do check >/dev/null; sleep 60; done
