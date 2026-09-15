#!/usr/bin/env bash
# 最终版构建: 翻译缓存已有译文时, 只做重排版, 可自选 字体/水印/原文层/体积.
#
# 用法(推荐交互, 直接跑不带参数):
#   ./scripts/build_final.sh [书.pdf]
# 或全参数模式:
#   ./scripts/build_final.sh 书.pdf --font serif --no-watermark --keep-original-layer
#
# 体积参考(751页实测):
#   默认(无原文层)          ~50MB
#   --keep-original-layer   ~540MB (保留英文原文层, 可搜索/复制)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then set -a; source "$ROOT/.env"; set +a; fi

DRYRUN=n
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then BOOK="$1"; shift; fi
: "${BOOK:=$(ls books/*.pdf 2>/dev/null | head -1 || true)}"
[ -n "$BOOK" ] || { echo "错误: books/ 下没有 PDF, 用法: $0 书.pdf [选项]"; exit 1; }

# ---------- 选项: 参数优先, 缺省交互 ----------
ask() { # $1=提示 $2=默认值 -> 回显选择
    if [ "${2:-}" = y ] || [ "${2:-}" = n ]; then
        local d=$2; [ "$d" = y ] && local h="Y/n" || local h="y/N"
        read -rp "$1 [$h]: " a; echo "${a:-$d}"
    else
        read -rp "$1 [$2]: " a; echo "${a:-$2}"
    fi
}

FONT="${FONT:-}"
WATERMARK="${WATERMARK:-}"
LAYER="${LAYER:-}"

if [ $# -eq 0 ]; then
    [ -z "$FONT" ]      && FONT=$(ask "正文字体? s=宋体(书籍风) / h=黑体(屏显)" s)
    [ -z "$WATERMARK" ] && WATERMARK=$(ask "保留水印署名? " n)
    [ -z "$LAYER" ]     && LAYER=$(ask "保留英文原文层? (体积约12倍) " n)
else
    while [ $# -gt 0 ]; do
        case "$1" in
            --font) FONT="$2"; shift 2;;
            --no-watermark) WATERMARK=n; shift;;
            --keep-watermark) WATERMARK=y; shift;;
            --keep-original-layer) LAYER=y; shift;;
            --dry-run) DRYRUN=y; shift;;
            *) echo "未知参数: $1"; exit 1;;
        esac
    done
fi

# ---------- 组装 flags ----------
FLAGS=(--min-text-length 5 --qps 16 --pool-max-workers 16
       --formular-font-pattern "(?!x)x" --no-dual)
case "$FONT" in
    s|serif) FLAGS+=(--primary-font-family serif);;
    h|sans)  :;;
    *) echo "FONT 只能是 s/h"; exit 1;;
esac
[ "$WATERMARK" = n ] && FLAGS+=(--watermark-output-mode no_watermark)
[ "$LAYER" = y ]     && FLAGS+=(--skip-clean)

if [ -f "$ROOT/prompts/book_prompt.txt" ]; then
    FLAGS+=(--custom-system-prompt "$(cat "$ROOT/prompts/book_prompt.txt")")
fi

# 自动页探测(跳过空白/扫描页 + EXCLUDE_PAGES)
if ! printf '%s\n' "$@" 2>/dev/null | grep -q '^--pages' && ! echo "$*" | grep -q -- '--pages'; then
    PAGES=$(uv run python - "$BOOK" <<'PYEOF'
import os, sys, pymupdf
doc = pymupdf.open(sys.argv[1])
exclude = set()
for part in os.environ.get("EXCLUDE_PAGES", "").split(","):
    if "-" in part:
        a, b = map(int, part.split("-")); exclude.update(range(a, b + 1))
    elif part:
        exclude.add(int(part))
good = [i + 1 for i in range(len(doc))
        if len(doc[i].get_text().strip()) >= 10 and i + 1 not in exclude]
ranges, start, prev = [], None, None
for p in good:
    if start is None: start = prev = p
    elif p == prev + 1: prev = p
    else:
        ranges.append(f"{start}-{prev}" if prev > start else str(start)); start = prev = p
if start is not None:
    ranges.append(f"{start}-{prev}" if prev > start else str(start))
print(",".join(ranges))
PYEOF
)
    FLAGS+=(--pages "$PAGES")
fi

OUT="${OUT:-$ROOT/output}"
mkdir -p "$OUT"
cd "$ROOT"
echo "构建配置: 字体=$FONT 水印=$WATERMARK 原文层=$LAYER"
echo "完整命令: uv run pdf2zh_next ${BOOK##*/} ${FLAGS[*]}"
[ "$DRYRUN" = y ] && { echo "(dry-run, 未执行)"; exit 0; }
echo "输出目录: $OUT (缓存命中的段落不会重新翻译)"
exec uv run pdf2zh_next "$BOOK" "${FLAGS[@]}" "$@"
