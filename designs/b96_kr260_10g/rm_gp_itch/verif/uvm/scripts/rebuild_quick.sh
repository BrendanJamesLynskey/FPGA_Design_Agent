#!/usr/bin/env bash
# rebuild only the bench (not the RTL snapshots' elaboration of the PAUSE=0 variant): for development
ITCH_BOTH=0 "$(dirname "$0")/uvm_build.sh" "$@"
