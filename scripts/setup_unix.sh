#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIRECTORY"

PYTHON_COMMAND="${PYTHON_COMMAND:-python3.11}"
"$PYTHON_COMMAND" --version

if [[ ! -x ".venv/bin/python" ]]; then
  "$PYTHON_COMMAND" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[actions]'
.venv/bin/python scripts/download_face_model.py
.venv/bin/python scripts/download_phone_model.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m driver_monitor.doctor

echo "安装与无摄像头检查完成。运行 ./启动疲劳监测.sh 即可启动。"
