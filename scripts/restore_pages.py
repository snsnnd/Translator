#!/usr/bin/env python3
"""把被排除的页面(空白页/目录页)用原书页面补回译文PDF, 恢复与原书一致的页数和页码.

原理: 译文PDF的第 k 页对应原书"第 k 个有效页"(有效页=字符数>=10 且不在排除列表)。
遍历原书逐页对齐: 有效页取译文, 无效页取原书原样插入。

用法:
    uv run scripts/restore_pages.py books/书.pdf output/书.zh.mono.pdf [-o 输出]
"""
import argparse
import os
from pathlib import Path

import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("translated")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--exclude", default=os.environ.get("EXCLUDE_PAGES", ""),
                    help="翻译时排除的页码, 如 7-12")
    args = ap.parse_args()

    src = pymupdf.open(args.book)
    tra = pymupdf.open(args.translated)

    # 与 parallel_translate 相同的有效页判定
    exclude = set()
    for part in args.exclude.split(","):
        if "-" in part:
            a, b = map(int, part.split("-"))
            exclude.update(range(a, b + 1))
        elif part:
            exclude.add(int(part))
    valid = [i for i in range(len(src))
             if len(src[i].get_text().strip()) >= 10 and (i + 1) not in exclude]
    if len(valid) != len(tra):
        raise SystemExit(f"页数不匹配: 有效页 {len(valid)} != 译文页 {len(tra)}, "
                         f"确认排除规则与翻译时一致 (--exclude {args.exclude!r})")

    out = pymupdf.open()
    t = 0
    for i in range(len(src)):
        if t < len(valid) and valid[t] == i:
            out.insert_pdf(tra, from_page=t, to_page=t)  # 译文页
            t += 1
        else:
            out.insert_pdf(src, from_page=i, to_page=i)  # 原书页原样保留
    out_path = args.out or args.translated
    out.save(out_path + ".tmp")
    out.close()
    Path(out_path + ".tmp").replace(out_path)
    print(f"完成: {out_path} 共 {len(src)} 页 "
          f"(译文 {t} 页 + 原书保留 {len(src) - t} 页)")


if __name__ == "__main__":
    main()
