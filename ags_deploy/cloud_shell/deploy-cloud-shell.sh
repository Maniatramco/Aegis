#!/usr/bin/env bash
# Run inside OCI Cloud Shell. The Windows deploy.ps1 route remains available.
set -euo pipefail
task_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${AEGIS_PYTHON:-}" ]]; then
    task_python="$AEGIS_PYTHON"
elif command -v python3.12 >/dev/null 2>&1; then
    task_python="$(command -v python3.12)"
else
    task_python="$(command -v python3)"
fi
exec "$task_python" -u -B -X utf8 "$task_script_dir/cloud_shell_release.py" "$@"
