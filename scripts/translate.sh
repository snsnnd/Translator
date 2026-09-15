#!/usr/bin/env bash
# PDF 批量翻译（英文 -> 中文，保留排版）
# 用法:
#   ./translate.sh 书.pdf                  # 全书翻译 (自动跳过空白/扫描页)
#   ./translate.sh 书.pdf --pages 100-200  # 指定页
# 可选流程:
#   uv run make_glossary.py 书.pdf         # 先读前言/目录生成专属术语表
#                                          # 之后 translate.sh 自动加载 book_prompt.txt
set -euo pipefail

# 自动加载本地 .env (含 API key)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
    set -a; source "$ROOT/.env"; set +a
fi

# API key: 优先 ZHIPU_API_KEY, 兼容自定义名 API_KEY_<名称> (取第一个)
API_KEY_VALUE="${ZHIPU_API_KEY:-}"
if [ -z "$API_KEY_VALUE" ] && [ -f "$ROOT/.env" ]; then
    API_KEY_VALUE=$(grep -m1 -E '^(API_KEY_|ZHIPU_API_KEY)' "$ROOT/.env" | cut -d= -f2- || true)
fi

# 第一个不以 -- 开头的参数是书名, 其余透传给 pdf2zh; 缺省取 books/ 下第一个 PDF
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
    BOOK="$1"; shift
else
    BOOK=$(ls books/*.pdf 2>/dev/null | head -1 || true)
    [ -z "$BOOK" ] && { echo "错误: books/ 下没有 PDF, 用法: $0 书.pdf [参数...]"; exit 1; }
fi

OUT="${OUT:-$ROOT/output}"
mkdir -p "$OUT"

# 未指定 --pages 时, 自动探测有效页 (跳过空白/纯图片页, 避免扫描版误报中断)
if ! printf '%s\n' "$@" | grep -q '^--pages'; then
    PAGES=$(uv run python - "$BOOK" <<'PYEOF'
import os, sys, pymupdf
doc = pymupdf.open(sys.argv[1])
exclude = set()
for part in os.environ.get("EXCLUDE_PAGES", "").split(","):
    if "-" in part:
        a, b = map(int, part.split("-"))
        exclude.update(range(a, b + 1))
    elif part:
        exclude.add(int(part))
good = [i + 1 for i in range(len(doc)) if len(doc[i].get_text().strip()) >= 10 and i + 1 not in exclude]
ranges, start, prev = [], None, None
for p in good:
    if start is None:
        start = prev = p
    elif p == prev + 1:
        prev = p
    else:
        ranges.append(f"{start}-{prev}" if prev > start else str(start))
        start = prev = p
if start is not None:
    ranges.append(f"{start}-{prev}" if prev > start else str(start))
print(",".join(ranges))
PYEOF
)
    set -- "$@" --pages "$PAGES"
fi

# 提示词: 优先用 make_glossary.py 生成的全书专属术语表
if [ -f "$ROOT/prompts/book_prompt.txt" ]; then
    PROMPT=$(cat "$ROOT/prompts/book_prompt.txt")
else
    PROMPT="You are a professional academic book translator. Translate English to Simplified Chinese with precision. Keep formulas, numbers and citations unchanged. Keep technical terminology professional and consistent."
fi

# qps/并发上限: 智谱免费额度实测 16 稳定, 报 429 就调小
# formular-font-pattern 设为永不匹配: 防止目录页码等被误判为公式字符,
# 导致 LLM 回传 <code> 标签被渲染成红色乱码的问题
cd "$ROOT"
exec uv run pdf2zh_next "$BOOK" "$@" \
    --zhipu \
    --zhipu-model glm-4-flash \
    --zhipu-api-key "$API_KEY_VALUE" \
    --output "$OUT" \
    --no-dual \
    --min-text-length 5 \
    --qps 16 \
    --pool-max-workers 16 \
    --formular-font-pattern "(?!x)x" \
    --custom-system-prompt "$PROMPT"
