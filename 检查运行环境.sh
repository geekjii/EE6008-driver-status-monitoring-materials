#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DOCTOR="$PROJECT_DIRECTORY/.venv/bin/driver-monitor-doctor"

if [[ ! -x "$DOCTOR" ]]; then
  echo "项目环境尚未安装。请先运行 scripts/setup_unix.sh。"
  exit 1
fi

cd "$PROJECT_DIRECTORY"
exec "$DOCTOR"
