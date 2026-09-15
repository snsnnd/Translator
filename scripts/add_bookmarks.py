#!/usr/bin/env python3
"""给译文 PDF 加书签: 复制原书 PDF outline 结构(页码与译文完全一致), 标题翻译成中文.

用法:
    uv run scripts/add_bookmarks.py books/原书.pdf output/译文.pdf
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
KEY = None
for line in open(ROOT / ".env"):
    if line.startswith("ZHIPU_API_KEY"):
        KEY = line.split("=", 1)[1].strip()
        break

MODEL = "glm-4-flash"
BATCH = 80


def translate_titles(titles: list[str]) -> list[str]:
    out = []
    for i in range(0, len(titles), BATCH):
        batch = titles[i:i + BATCH]
        lines = "\n".join(f"{j}|{t}" for j, t in enumerate(batch))
        body = json.dumps({
            "model": MODEL, "temperature": 0.1,
            "messages": [{"role": "user", "content":
                "把下面每行书签标题翻译成简体中文(专业书籍目录风格, 简洁准确). "
                "保留原编号(如 Chapter 3/3.4.2 等译为 第3章/3.4.2). "
                "每行严格保持 '序号|译文' 格式, 不要增删行:\n\n" + lines}],
        }).encode()
        req = urllib.request.Request(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions", data=body,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=300))
        text = d["choices"][0]["message"]["content"]
        got = {}
        for line in text.splitlines():
            m = re.match(r"\s*(\d+)\s*\|\s*(.+)", line)
            if m:
                got[int(m.group(1))] = m.group(2).strip()
        for j, t in enumerate(batch):
            out.append(got.get(j, t))  # 失配时回退英文原标题
        print(f"  批次 {i // BATCH + 1}: {len(got)}/{len(batch)} 条翻译成功")
        time.sleep(1)
    return out


def main():
    src = pymupdf.open(sys.argv[1])
    dst = pymupdf.open(sys.argv[2])
    toc = src.get_toc()
    if not toc:
        raise SystemExit("原书没有书签")
    print(f"原书书签 {len(toc)} 条, 翻译标题...")
    titles = translate_titles([re.sub(r"\s+", " ", t[1]).strip() for t in toc])
    new_toc = [[lvl, title, page] for (lvl, _, page), title in zip(toc, titles)]
    dst.set_toc(new_toc)
    out = sys.argv[2] + ".tmp"
    dst.save(out)
    dst.close()
    Path(out).replace(sys.argv[2])
    print(f"完成: {sys.argv[2]} 已写入 {len(new_toc)} 条中文书签")


import pymupdf
if __name__ == "__main__":
    main()
