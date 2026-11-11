#!/usr/bin/env bash
# fetch_results.sh: python3 cloud/fda_cloud.py fetch-results (see cloud/README.md). The owner runs it: it uses the owner's AWS login.
exec python3 "$(dirname "$0")/fda_cloud.py" fetch-results "$@"
