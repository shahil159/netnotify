#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then echo "Create the venv and install requirements first (see README.md)." >&2; exit 1; fi
source .venv/bin/activate
exec python client.py "$@"
