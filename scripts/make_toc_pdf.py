#!/usr/bin/env python3
"""从原书目录页提取文本, 用 LLM 生成干净的中英对照目录, 输出为独立 PDF.

用法:
    uv run make_toc_pdf.py 书.pdf [--pages 7-12] [--out output/目录_中英对照.pdf]
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path

KEY = None
for line in open(Path(__file__).parent.parent / ".env"):
    if line.startswith("ZHIPU_API_KEY="):
        KEY = line.split("=", 1)[1].strip()

PROMPT = """以下是一本英文技术书的目录文本。注意: 文本提取时字母间可能被插入了多余空格(如 "I n t r o d u c t i o n" 实为 "Introduction"), 页码数字间也可能有空格(如 "1 2" 实为 "12"), 请先在脑中还原再处理。

还原成结构化目录并输出中英对照, 每行严格用 " || " 分隔四个字段:

编号 || 页码 || 中文标题 || English Title

要求:
1. 编号: 章用 "CH: 1" 格式, 节用原编号如 "1.1"、"2.3.1"; 没有编号的前置部分(前言/缩略语表等)用 "FM: 1"、"FM: 2" 递增
2. 页码: 还原成正常数字(阿拉伯或罗马), 去掉所有内部空格
3. 中文标题: 将英文标题准确翻译成专业简体中文, 禁止输出"章标题/节标题"之类占位词
4. English Title: 还原后的原始英文标题
5. 只输出目录行, 不要任何解释或代码块标记

目录文本:
"""


def extract(book: str, pages: list[int]) -> str:
    import pymupdf

    doc = pymupdf.open(book)
    text = "\n".join(doc[i - 1].get_text() for i in pages if i <= len(doc))
    doc.close()
    return text[:14000]


def ask_llm(content: str) -> str:
    body = json.dumps({
        "model": "glm-4.5-flash", "temperature": 0.1,
        "messages": [{"role": "user", "content": content}],
    }).encode()
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=body, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]


def build_pdf(rows: list[tuple[str, str, str]], out: str):
    import pymupdf

    doc = pymupdf.open()
    W, H = 595, 842  # A4
    M, LH = 60, 17
    font = pymupdf.Font("china-s")
    page = None
    y = 0

    def new_page():
        nonlocal page, y
        page = doc.new_page()
        page.insert_text((M, 70), "目 录  (中英对照)", fontsize=16, fontname="china-s")
        page.insert_text((M, 88), "Bilingual Table of Contents", fontsize=9, color=(0.4, 0.4, 0.4))
        y = 115

    RX = re.compile(r"^[xXvViI\\d ]+$")

    def put(x, text, size, color=(0, 0, 0)):
        nonlocal y
        if y > H - 60:
            new_page()
        if font.text_length(text, size) > W - M - x:
            while text and font.text_length(text + "…", size) > W - M - x:
                text = text[:-1]
            text += "…"
        page.insert_text((x, y), text, fontsize=size, fontname="china-s", color=color)
        y += LH

    new_page()
    for no, pg, zh, en in rows:
        pg = re.sub(r"(?<=[xXvViI0-9]) (?=[xXvViI0-9])", "", pg)  # 去掉页码内部空格
        if no.startswith("CH:"):
            y += 8
            put(M, f"{no[3:]}  {zh}  ·  {pg}", 12.5, (0.05, 0.25, 0.5))
            put(M + 14, en, 9.5, (0.4, 0.4, 0.4))
            y += 3
        else:
            put(M + 20, f"{no}  {zh}  ·  {pg}", 10.5)
            put(M + 34, en, 8.5, (0.45, 0.45, 0.45))
    doc.save(out)
    doc.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--pages", default="7-12")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "output" / "目录_中英对照.pdf"))
    args = ap.parse_args()

    text = extract(args.book, list(map(int, args.pages.split("-"))))
    print(f"提取目录文本 {len(text)} 字符, 请求 LLM...")
    raw = ask_llm(PROMPT + text)

    rows = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("||")]
        if len(parts) == 4 and parts[0] and not parts[0].startswith("#"):
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    print(f"解析出 {len(rows)} 条目录行")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    build_pdf(rows, args.out)
    print(f"已生成: {args.out}")


if __name__ == "__main__":
    main()
