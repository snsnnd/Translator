#!/usr/bin/env python3
"""多进程并行 PDF 翻译编排器: 把书拆成 N 段, 每段开一个独立 pdf2zh 进程(各自 16 并发),
实时显示进度/速度/剩余时间, 全部完成后按顺序合并成一个 PDF.

用法:
    uv run parallel_translate.py [书.pdf] [--workers 3] [--from 3] [--to 751] [--qps 16]
    uv run parallel_translate.py --status   # 只查看已在运行的进度
"""
import argparse
import datetime as _dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
QPS_PER_WORKER = 16
PROGRESS_RE = re.compile(r"translate\s+.*?(\d+)/(\d+)\s+(\S+)\s+(\S+)")


def load_env():
    env = dict(os.environ)
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def valid_pages(book: str) -> list[int]:
    import pymupdf

    doc = pymupdf.open(book)
    pages = [i + 1 for i in range(len(doc)) if len(doc[i].get_text().strip()) >= 10]
    doc.close()
    return pages


def split_ranges(pages: list[int], n: int) -> list[list[int]]:
    chunks = [[] for _ in range(n)]
    for i, p in enumerate(pages):
        chunks[i % n].append(p)
    out = []
    for c in chunks:
        ranges, start, prev = [], None, None
        for p in c:
            if start is None:
                start = prev = p
            elif p == prev + 1:
                prev = p
            else:
                ranges.append(f"{start}-{prev}" if prev > start else str(start))
                start = prev = p
        if start is not None:
            ranges.append(f"{start}-{prev}" if prev > start else str(start))
        out.append(",".join(ranges))
    return out


def fmt_hms(sec: float) -> str:
    if sec is None or sec != sec or sec < 0:
        return "--"
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def worker_status(log_path: Path) -> tuple[int, int, float, float] | None:
    """从日志解析 (已完成, 总数, 已用秒, 预计剩余秒)."""
    if not log_path.exists():
        return None
    m = None
    with open(log_path, errors="ignore") as f:
        for line in f:
            if "translate" in line.lower():
                mm = PROGRESS_RE.search(line)
                if mm:
                    m = mm
    if not m:
        return None
    done, total = int(m.group(1)), int(m.group(2))
    elapsed = m.group(3)
    eta = m.group(4)
    def to_sec(s):
        parts = [float(x) for x in s.split(":")]
        return sum(x * 60**i for i, x in enumerate(reversed(parts)))
    return done, total, to_sec(elapsed), to_sec(eta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", default=None)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=10**6)
    ap.add_argument("--exclude", default="", help="不翻译的页码, 如 7-12")
    ap.add_argument("--serif", action="store_true", help="正文用宋体(衬线)")
    ap.add_argument("--no-watermark", action="store_true", help="去水印署名")
    ap.add_argument("--skip-clean", action="store_true", help="保留原文层(可搜索)")
    ap.add_argument("--qps", type=int, default=QPS_PER_WORKER)
    ap.add_argument("--custom-system-prompt", default=None)
    args = ap.parse_args()

    # 未指定书名时自动取 books/ 下第一个 PDF
    if args.book is None:
        candidates = sorted((ROOT / "books").glob("*.pdf"))
        if not candidates:
            ap.error("请提供书.pdf 或把 PDF 放进 books/ 目录")
        args.book = str(candidates[0])

    env = load_env()
    prompt_file = ROOT / "prompts" / "book_prompt.txt"
    prompt = args.custom_system_prompt
    if prompt is None and prompt_file.exists():
        prompt = prompt_file.read_text()

    exclude = set()
    for part in args.exclude.split(","):
        if "-" in part:
            a, b = map(int, part.split("-"))
            exclude.update(range(a, b + 1))
        elif part:
            exclude.add(int(part))
    pages = [p for p in valid_pages(args.book) if args.start <= p <= args.end and p not in exclude]
    chunk_lists = [[] for _ in range(args.workers)]
    for i, p in enumerate(pages):
        chunk_lists[i % args.workers].append(p)
    chunks = split_ranges(pages, args.workers)
    total_pages = len(pages)
    print(f"共 {total_pages} 个有效页, 分 {args.workers} 个进程: {[len(c) for c in chunks]}")

    parts_dir = ROOT / "output" / "parts"
    logs_dir = ROOT / "logs"
    parts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    base = ["uv", "run", "pdf2zh_next", args.book,
            "--zhipu", "--zhipu-model", "glm-4-flash",
            "--zhipu-api-key", env["ZHIPU_API_KEY"],
            "--no-dual", "--min-text-length", "5",
            "--qps", str(args.qps), "--pool-max-workers", str(args.qps),
            "--formular-font-pattern", "(?!x)x",
            "--only-include-translated-page"]
    if args.serif:
        base += ["--primary-font-family", "serif"]
    if args.no_watermark:
        base += ["--watermark-output-mode", "no_watermark"]
    if args.skip_clean:
        base += ["--skip-clean"]
    if prompt:
        base += ["--custom-system-prompt", prompt]

    # key 池: 支持自定义名称 API_KEY_<任意名> (推荐), 兼容旧 ZHIPU_API_KEY(_N)
    keys = sorted(v for k, v in env.items()
                  if k.startswith("API_KEY_") or k.startswith("ZHIPU_API_KEY"))
    print(f"可用 API key: {len(keys)} 个")

    procs = []
    t0 = time.time()
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        log = open(logs_dir / f"part{i}.log", "w")
        p = subprocess.Popen(
            base[:4] + ["--zhipu", "--zhipu-model", "glm-4-flash",
             "--zhipu-api-key", keys[i % len(keys)],
             "--pages", chunk, "--output", str(parts_dir / f"part{i}")]
            + base[base.index("--no-dual"):],
            stdout=log, stderr=subprocess.STDOUT,
            env={**env, "COLUMNS": "250"},  # 让 rich 进度条不截断, 便于解析
            cwd=ROOT)
        procs.append((i, p, len(chunk), t0))
        print(f"  worker{i}: {len(chunk)}页 pid={p.pid}")

    status_path = ROOT / "logs" / "status.json"
    started_iso = _dt.datetime.now().isoformat(timespec="seconds")

    def write_status(phase, workers, done, total, speed, eta, extra=None):
        """前端轮询接口: 每个监控周期把结构化进度写入 logs/status.json"""
        payload = {
            "book": args.book, "phase": phase, "started_at": started_iso,
            "updated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "workers": workers,
            "total": {"pages": total, "done": done,
                      "percent": round(done / max(total, 1) * 100, 1),
                      "speed_pages_per_min": round(speed, 2) if speed is not None else None,
                      "eta_seconds": round(eta) if eta is not None else None},
        }
        if extra:
            payload.update(extra)
        status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))

    print("\n实时进度 (每30秒刷新, Ctrl+C 退出监控不影响后台翻译):\n")
    try:
        while any(p.poll() is None for _, p, _, _ in procs):
            lines, total_done, total_pages_all = [], 0, 0
            wstatus = []
            for i, p, npages, start_t in procs:
                st = worker_status(logs_dir / f"part{i}.log")
                if p.poll() is not None:
                    code = p.returncode
                    lines.append(f"  worker{i}: {'完成' if code == 0 else f'退出(code={code})'}  ({npages}页)")
                    wstatus.append({"id": i, "state": "done" if code == 0 else "failed",
                                    "pages_done": npages if code == 0 else None,
                                    "pages_total": npages})
                    if code == 0:
                        total_done += npages
                    total_pages_all += npages
                    continue
                if st:
                    done, tot, el, eta = st
                    speed = done / el * 60 if el > 5 else 0
                    lines.append(f"  worker{i}: {done}/{tot}页  已用{fmt_hms(el)}  剩余~{fmt_hms(eta)}  {speed:.1f}页/分")
                    wstatus.append({"id": i, "state": "running", "pages_done": done,
                                    "pages_total": tot, "elapsed_sec": int(el),
                                    "eta_sec": int(eta)})
                    total_done += done
                    total_pages_all += tot
                else:
                    lines.append(f"  worker{i}: 启动/解析中...")
                    wstatus.append({"id": i, "state": "parsing", "pages_total": npages})
                    total_pages_all += npages
            agg = total_done / (time.time() - t0) * 60 if time.time() - t0 > 30 else 0
            remain = total_pages_all - total_done
            eta_all = remain / agg * 60 if agg > 0 else None
            write_status("running", wstatus, total_done, total_pages_all,
                         agg, eta_all)
            print(f"[{time.strftime('%H:%M:%S')}] 总进度 {total_done}/{total_pages_all} ({total_done / max(total_pages_all,1) * 100:.0f}%)"
                  f"  合计{agg:.1f}页/分  预计剩余 {fmt_hms(eta_all) if eta_all else '计算中'}")
            print("\n".join(lines) + "\n")
            time.sleep(30)
    except KeyboardInterrupt:
        write_status("detached", [], 0, total_pages, None, None,
                     {"note": "监控已退出, 后台翻译继续运行"})
        print("\n监控已退出, 后台翻译继续运行。查看进度: uv run parallel_translate.py --status")
        return

    ok = all(p.returncode == 0 for _, p, _, _ in procs)
    print(f"\n全部进程结束, {'开始合并' if ok else '注意: 有进程失败'}")
    write_status("merging" if ok else "failed", [], total_pages, total_pages,
                 None, 0, {"output": None})

    if ok:
        import pymupdf
        merged = pymupdf.open()
        for i, _, _, _ in procs:
            f = parts_dir / f"part{i}" / (Path(args.book).stem + ".zh.mono.pdf")
            if f.exists():
                with pymupdf.open(f) as part:
                    merged.insert_pdf(part)
                print(f"  已合并 part{i} ({len(pymupdf.open(f))}页)")
        # 恢复原书被排除的页面(空白页/目录页), 保持与原书页码一致
        # 注意: 分片是轮转分配的, 必须按 chunk_lists 精确映射译文页 -> 原书页
        # --no-watermark 会使 BabelDOC 产物文件名带 .no_watermark 中缀
        mid = ".no_watermark" if args.no_watermark else ""
        final = pymupdf.open()
        src = pymupdf.open(args.book)
        final.insert_pdf(src)  # 先全部用原书, 再用译文替换有效页
        page_owner = {}        # 原书页码(1-based) -> (part序号, part内局部页码)
        for ci, cl in enumerate(chunk_lists):
            for j, p in enumerate(cl):
                page_owner[p] = (ci, j)
        for p, (ci, j) in sorted(page_owner.items()):
            f = parts_dir / f"part{ci}" / (Path(args.book).stem + mid + ".zh.mono.pdf")
            part = pymupdf.open(f)
            final.delete_page(p - 1)
            final.insert_pdf(part, from_page=j, to_page=j, start_at=p - 1)
            part.close()
        merged.close()
        out = ROOT / "output" / (Path(args.book).stem + ".zh.mono.pdf")
        final.save(out)
        final.close()
        t = len(pages)
        print(f"合并完成: {out} 共 {len(src)} 页 "
              f"(译文 {t} + 原书保留 {len(src) - t})")
        write_status("done", [], t, len(src), None, 0,
                     {"output": str(out)})


if __name__ == "__main__":
    main()
