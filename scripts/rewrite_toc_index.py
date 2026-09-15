#!/usr/bin/env python3
"""目录/索引区域重写: 从原书提取"标题+页码"行结构, 标题翻译成中文后按原坐标重绘.

原理: 目录/索引是"表格型文本"(标题列+页码列), BabelDOC 按流式段落处理必然粘连.
本脚本绕开 BabelDOC: pymupdf 按视觉行(共享基线)提取原书文本 → LLM 只翻标题 →
按原 bbox 重绘, 页码/缩进/双栏全部保留, 替换译文 PDF 中对应页.

用法:
    uv run scripts/rewrite_toc_index.py books/原书.pdf output/译文.pdf
    # 目录/索引页码自动从书签探测, 也可 --toc 7-12 --index 717-750 手动指定
"""
import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

import pymupdf

ROOT = Path(__file__).parent.parent
KEY = None
for line in open(ROOT / ".env"):
    if line.startswith("ZHIPU_API_KEY"):
        KEY = line.split("=", 1)[1].strip()
        break

NUM = re.compile(r"^[\d][\d,\u2013\- ]*$")            # 索引页码列表: "10, 27, 212"
PAGENUM = re.compile(r"^[0-9]+$|^[ivxlcdm]+$", re.I)  # 目录页码: "12" / "xvii"
BATCH = 80
Y_TOL = 3.5          # 同一视觉行的 y 容差(pt)
FONT = pymupdf.Font("china-s")


# ---------- 视觉行提取 ----------

def rows_of(page) -> list[list[dict]]:
    """把页面 span 按 y 中心聚成视觉行, 行内按 x 排序. 返回 span 列表的列表."""
    segs = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    segs.append(s)
    segs.sort(key=lambda s: ((s["bbox"][1] + s["bbox"][3]) / 2, s["bbox"][0]))
    rows, cur_yc = [], None
    for s in segs:
        yc = (s["bbox"][1] + s["bbox"][3]) / 2
        if rows and abs(yc - cur_yc) <= Y_TOL:
            rows[-1].append(s)
            cur_yc = (cur_yc + yc) / 2
        else:
            rows.append([s])
            cur_yc = yc
    for r in rows:
        r.sort(key=lambda s: s["bbox"][0])
    return rows


def split_columns(segs, boundary):
    """把单个视觉行按 x0 是否越过 boundary 拆成左右栏(索引双栏页用)."""
    left = [s for s in segs if s["bbox"][0] < boundary]
    right = [s for s in segs if s["bbox"][0] >= boundary]
    return [col for col in (left, right) if col]


# ---------- 行分类 ----------

def classify_toc_row(segs):
    last = segs[-1]["text"].strip()
    if PAGENUM.match(last) and len(segs) > 1:
        return "toc_entry", segs[:-1], segs[-1:]
    return "toc_title", segs, []


def classify_index_row(segs):
    nums = [s for s in segs if NUM.match(s["text"].strip())]
    terms = [s for s in segs if not NUM.match(s["text"].strip())]
    if nums and terms:
        return "index_entry", terms, nums
    return "keep", segs, []


# ---------- LLM 翻译 ----------

def translate_batch(items: dict[str, str]) -> dict[str, str]:
    result, uids = {}, list(items)
    for i in range(0, len(uids), BATCH):
        batch = uids[i:i + BATCH]
        lines = "\n".join(f"{u}|{items[u]}" for u in batch)
        body = json.dumps({
            "model": "glm-4-flash", "temperature": 0.1,
            "messages": [{"role": "user", "content":
                "以下是书籍目录/索引条目的英文标题. 翻译成简洁专业的简体中文书目标题风格. "
                "规则: Chapter 3 译为 第3章; 保留 1.1/2.3.1 等编号原样; "
                "缩写用通行中文译名或保留英文; "
                "每行严格保持 'id|译文' 格式, 不要增删行:\n\n" + lines}],
        }).encode()
        req = urllib.request.Request(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions", data=body,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        for attempt in range(6):   # 429退避重试: 5s起指数增长
            try:
                d = json.load(urllib.request.urlopen(req, timeout=300))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 5:
                    wait = 5 * 2 ** attempt
                    print(f"  429限流, {wait}s后重试({attempt + 1}/5)")
                    time.sleep(wait)
                else:
                    raise
        for line in d["choices"][0]["message"]["content"].splitlines():
            m = re.match(r"\s*(\S+)\s*\|\s*(.+)", line)
            if m and m.group(1) in items:
                result[m.group(1)] = m.group(2).strip()
        print(f"  已翻译 {min(i + BATCH, len(uids))}/{len(uids)} 条")
        time.sleep(1)
    return result


# ---------- 重绘 ----------

def draw_text(page, x, y, text, size, right=None, max_x=None, color=(0, 0, 0)):
    tw = FONT.text_length(text, size)
    if max_x and x + tw > max_x and tw > 0:
        size = max(size * (max_x - x) / tw, 4)
        tw = FONT.text_length(text, size)
    if right is not None:
        x = right - tw
    page.insert_text((x, y), text, fontsize=size, fontname="china-s", color=color)


def rebuild_page(src, pno, jobs):
    page = src[pno - 1]
    for job in jobs.values():
        r = pymupdf.Rect(job["segs"][0]["bbox"])
        for s in job["segs"][1:]:
            r |= pymupdf.Rect(s["bbox"])
        page.add_redact_annot(r + (-1, -1, 1, 1))
    try:
        page.apply_redactions(graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    except TypeError:
        page.apply_redactions()

    for job in jobs.values():
        kind, zh, t0 = job["kind"], job.get("zh") or job["text"], job["segs"][0]
        if kind == "toc_entry":
            num = job["nums"][0]
            draw_text(page, t0["origin"][0], t0["origin"][1], zh, t0["size"],
                      max_x=num["bbox"][0] - 4)
            draw_text(page, 0, num["origin"][1], num["text"].strip(), num["size"],
                      right=num["bbox"][2])
        elif kind == "index_entry":
            draw_text(page, t0["origin"][0], t0["origin"][1], zh, t0["size"],
                      max_x=job["col_end"] - 8)
            term_end = t0["origin"][0] + FONT.text_length(zh, t0["size"])
            for ns in job["nums"]:
                x = max(ns["origin"][0], term_end + 6)
                draw_text(page, x, ns["origin"][1], ns["text"].strip(), ns["size"])
        elif kind in ("toc_title", "index_title"):
            draw_text(page, t0["origin"][0], t0["origin"][1], zh, t0["size"],
                      max_x=page.rect.width - 40)
        # kind == keep: 不动
    return page


# ---------- 页码探测 ----------

def detect_toc(src):
    for lvl, title, p in src.get_toc():
        if title.strip().lower().startswith("contents"):
            end, w = p, src[p - 1].rect.width
            while end <= len(src):
                rows = rows_of(src[end - 1])
                n_num = sum(1 for sp in rows if PAGENUM.match(sp[-1]["text"].strip()))
                if rows and n_num / len(rows) < 0.5:
                    break
                end += 1
            return p, end - 1
    return None, None


def detect_index(src):
    for lvl, title, p in src.get_toc():
        if re.fullmatch(r"index", title.strip(), re.I):
            last, p_ = p, p
            while p_ <= len(src):
                t = src[p_ - 1].get_text()
                if "WILEY END USER" in t or not t.strip():
                    break
                last = p_
                p_ += 1
            return p, last
    return None, None


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("translated")
    ap.add_argument("--toc", default="auto")
    ap.add_argument("--index", default="auto")
    args = ap.parse_args()

    src = pymupdf.open(args.book)
    toc_range = detect_toc(src) if args.toc == "auto" else \
        tuple(int(x) for x in args.toc.split("-"))
    idx_range = detect_index(src) if args.index == "auto" else \
        tuple(int(x) for x in args.index.split("-"))
    print(f"目录页: {toc_range}, 索引页: {idx_range}")

    jobs_by_page: dict[int, dict[str, dict]] = {}
    texts: dict[str, str] = {}

    def add_job(pno, rid, kind, text, segs, **meta):
        jobs_by_page.setdefault(pno, {})[rid] = {
            "kind": kind, "text": text, "segs": segs, "rid": rid, **meta}
        if kind != "keep":
            texts[rid] = text

    # 目录页(单栏)
    if toc_range[0]:
        for pno in range(toc_range[0], toc_range[1] + 1):
            for ri, segs in enumerate(rows_of(src[pno - 1])):
                kind, title, nums = classify_toc_row(segs)
                text = " ".join(s["text"].strip() for s in title)
                if not text.strip():
                    continue
                add_job(pno, f"p{pno}r{ri}", kind, text, segs, nums=nums)

    # 索引页(双栏)
    if idx_range[0]:
        for pno in range(idx_range[0], idx_range[1] + 1):
            page = src[pno - 1]
            for ri, row in enumerate(rows_of(page)):
                for ci, segs in enumerate(split_columns(row, page.rect.width / 2)):
                    kind, terms, nums = classify_index_row(segs)
                    text = " ".join(s["text"].strip() for s in terms)
                    if kind == "keep" or not re.search(r"[A-Za-z]{2}", text):
                        continue
                    col_end = page.rect.width / 2 if ci == 0 else page.rect.width - 34
                    add_job(pno, f"p{pno}r{ri}c{ci}", "index_entry", text, segs,
                            nums=nums, col_end=col_end)

    print(f"待翻译条目: {len(texts)}")
    zh = translate_batch(texts)
    for jobs in jobs_by_page.values():
        for job in jobs.values():
            if job["kind"] != "keep":
                job["zh"] = zh.get(job["rid"])

    for pno in jobs_by_page:
        rebuild_page(src, pno, jobs_by_page[pno])

    fin = pymupdf.open(args.translated)
    saved_toc = fin.get_toc()
    out = pymupdf.open()
    for i in range(len(fin)):
        pno = i + 1
        if pno in jobs_by_page:
            out.insert_pdf(src, from_page=pno - 1, to_page=pno - 1)
        else:
            out.insert_pdf(fin, from_page=i, to_page=i)
    if saved_toc:
        out.set_toc(saved_toc)
    tmp = args.translated + ".tmp"
    out.save(tmp)
    out.close()
    Path(tmp).replace(args.translated)
    print(f"完成: {args.translated} (重写 {len(jobs_by_page)} 页, 页数不变 {len(fin)})")


if __name__ == "__main__":
    main()
