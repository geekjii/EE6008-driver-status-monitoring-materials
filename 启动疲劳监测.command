#!/bin/zsh

set -e

PROJECT_DIRECTORY="${0:A:h}"
cd "$PROJECT_DIRECTORY"

WEB_LAUNCHER="$PROJECT_DIRECTORY/.venv/bin/driver-monitor-web"

if [[ ! -x "$WEB_LAUNCHER" ]]; then
  echo "项目环境尚未安装，请先按照 README.md 完成第一次安装。"
  read -r "?按回车键关闭窗口..."
  exit 1
fi

"$WEB_LAUNCHER"
LAUNCH_STATUS=$?

if (( LAUNCH_STATUS != 0 )); then
  echo
  echo "启动失败，错误代码：$LAUNCH_STATUS"
  echo "请把上面的错误内容发给AI继续排查。"
  read -r "?按回车键关闭窗口..."
fi

exit "$LAUNCH_STATUS"
