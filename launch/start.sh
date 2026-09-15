#!/usr/bin/env bash
# PDF 翻译器 一键启动器 (Linux / macOS)
# 运行后自动打开浏览器; Ctrl+C 停止服务
cd "$(dirname "$0")/.."

# 3 秒后自动打开浏览器 (给服务器留启动时间)
( sleep 3
  xdg-open http://localhost:8000 2>/dev/null \
  || open http://localhost:8000 2>/dev/null ) &

exec uv run web/server/main.py
