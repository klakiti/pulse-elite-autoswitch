#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$project_dir/build-deb.py"
printf 'Packages built in %s/dist. Install the core and optional desktop package with apt; see README.md.\n' "$project_dir"
