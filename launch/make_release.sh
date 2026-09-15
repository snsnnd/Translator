#!/usr/bin/env bash
# 构建发布包: Translator-portable-<日期>.zip
# 内容: 源码 + 已构建前端(web/dist) + Windows 版 uv.exe
# 接收者: 解压 -> 双击 launch/install.bat -> 双击 launch/启动翻译器.bat
# 用法: ./launch/make_release.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP=$(date +%Y%m%d)
STAGE=$(mktemp -d)/Translator
trap 'rm -rf "$(dirname "$STAGE")"' EXIT

mkdir -p "$STAGE"

# 1) 复制源码(排除本地数据/密钥/大文件)
tar -cf - \
    --exclude=.git --exclude=.venv --exclude='**/__pycache__' \
    --exclude='books/*' --exclude='output/*' --exclude='logs/*' \
    --exclude='web/node_modules' --exclude='prompts/book_prompt.txt' \
    --exclude='.env' \
    . | tar -C "$STAGE" -xf -

# 2) 前端产物(必须已构建)
[ -d web/dist ] || { echo "错误: web/dist 不存在, 先执行 cd web && npm install && npm run build"; exit 1; }

# 3) 内置 Windows 版 uv (接收者免单独安装 uv)
curl -fsSL -o "$STAGE/launch/uv-win.zip" \
    https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip

# 4) 打包
OUT="$ROOT/Translator-portable-$STAMP.zip"
(cd "$(dirname "$STAGE")" && zip -qr "$OUT" Translator)
echo "✓ 发布包已生成: $OUT ($(du -h "$OUT" | cut -f1))"
echo "  分发时提醒用户: 解压后先运行 launch/install.bat"
