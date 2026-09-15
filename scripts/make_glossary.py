#!/usr/bin/env python3
"""从书的前言/目录提取内容, 让 LLM 生成全书专属翻译术语表和风格指南.

用法:
    uv run make_glossary.py 书.pdf [--pages 3-15] [--out book_prompt.txt]
生成的 book_prompt.txt 会被 translate.sh 自动用作 --custom-system-prompt.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

KEY = None
for line in open(Path(__file__).parent.parent / ".env"):
    line = line.strip()
    # 兼容两种写法: 旧 ZHIPU_API_KEY= 优先, 新自定义名 API_KEY_<名称>=
    if line.startswith("ZHIPU_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
        break
    if KEY is None and line.startswith("API_KEY_") and "=" in line:
        KEY = line.split("=", 1)[1].strip()

META_PROMPT = """以下是一本英文技术书籍的标题页、目录和前言节选。请为翻译这本书生成一份中文翻译指南，输出两部分:

1. 【术语表】30-50 个该书核心术语的固定译法，每行一个，格式: 英文=中文
   (必须是这个领域内通行、专业的中文译名，不要自创)

2. 【风格】3-5 行简短的翻译风格要求(人名/文献引用/公式的处理方式等)

只输出指南本身，不要任何额外说明。

书的内容节选:
"""


def extract_text(pdf_path: str, pages: list[int]) -> str:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    chunks = []
    for i in pages:
        if i < len(doc):
            t = doc[i].get_text().strip()
            if t:
                chunks.append(t)
    return "\n".join(chunks)[:12000]  # 截断, 控制token


def ask_llm(content: str) -> str:
    body = json.dumps({
        "model": "glm-4-flash",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是学术翻译专家。"},
            {"role": "user", "content": content},
        ],
    }).encode()
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    d = json.load(urllib.request.urlopen(req, timeout=300))
    return d["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="3-15", help="用于生成术语表的页码范围")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "prompts" / "book_prompt.txt"))
    args = ap.parse_args()

    pages = []
    for part in args.pages.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.extend(range(int(a) - 1, int(b)))
        else:
            pages.append(int(part) - 1)

    print(f"提取 {args.pdf} 第 {args.pages} 页文本...")
    text = extract_text(args.pdf, pages)
    print(f"共 {len(text)} 字符, 请求 LLM 生成术语表...")

    guide = ask_llm(META_PROMPT + text)
    prompt = (
        "You are a professional academic book translator. Translate English to "
        "Simplified Chinese with precision. Follow this style guide strictly:\n\n"
        + guide
    )
    with open(args.out, "w") as f:
        f.write(prompt)
    print(f"已写入 {args.out}:\n")
    print(guide)


if __name__ == "__main__":
    main()
