#!/usr/bin/env bash
# run_batch.sh: python3 cloud/fda_cloud.py run-batch (see cloud/README.md). The owner runs it: it uses the owner's AWS login.
exec python3 "$(dirname "$0")/fda_cloud.py" run-batch "$@"
