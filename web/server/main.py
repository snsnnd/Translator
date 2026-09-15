#!/usr/bin/env python3
"""Web 后端壳: 只做三件事
1. subprocess 启动翻译/后处理脚本 (零侵入, 不改现有脚本)
2. 读 logs/status.json 等文件转成 JSON API
3. 静态托管 web/dist (前端) 与 output/ (产物预览/下载)

启动: uv run web/server/main.py   →  http://localhost:8000
"""
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent
BOOKS = ROOT / "books"
OUTPUT = ROOT / "output"
LOGS = ROOT / "logs"
PROMPTS = ROOT / "prompts"
DIST = Path(__file__).resolve().parent.parent / "dist"

app = FastAPI(title="PDF Translator Web")

# ---------------------------------------------------------------- job runner
_jobs: dict[str, dict] = {}
_job_seq = 0
_job_lock = threading.Lock()


def _run_job(job_id: str, cmd: list[str], cwd: Path = ROOT, env: dict | None = None):
    log_path = LOGS / f"web_job_{job_id}.log"
    with log_path.open("w") as lf:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
            env=env or os.environ.copy(), start_new_session=True,
        )
        _jobs[job_id].update(pid=proc.pid, state="running")
        rc = proc.wait()
        _jobs[job_id].update(state="done" if rc == 0 else "failed", returncode=rc, ended=time.time())
        if _jobs[job_id]["label"].startswith(("translate:", "post:")):
            organize_output()  # 任务结束顺手把产物按书名归档


def _run_chained(job_id: str, steps: list[list[str]]):
    """顺序执行多步命令(如: 先术语表→再翻译), 任一步失败即止"""
    log_path = LOGS / f"web_job_{job_id}.log"
    with log_path.open("w") as lf:
        _jobs[job_id].update(state="running")
        for i, cmd in enumerate(steps, 1):
            lf.write(f"\n===== step {i}/{len(steps)}: {' '.join(cmd)} =====\n")
            lf.flush()
            proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT,
                env=os.environ.copy(), start_new_session=True,
            )
            _jobs[job_id].update(pid=proc.pid)
            rc = proc.wait()
            if rc != 0:
                _jobs[job_id].update(state="failed", returncode=rc, ended=time.time(), failed_step=i)
                return
        _jobs[job_id].update(state="done", returncode=0, ended=time.time())
        organize_output()  # 翻译任务结束顺手把产物按书名归档


def start_job(label: str, cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> dict:
    global _job_seq
    with _job_lock:
        _job_seq += 1
        job_id = f"{int(time.time())}_{_job_seq}"
        _jobs[job_id] = {"id": job_id, "label": label, "cmd": cmd, "state": "queued",
                         "started": time.time(), "log": str(LOGS / f"web_job_{job_id}.log")}
    threading.Thread(target=_run_job, args=(job_id, cmd, cwd, env), daemon=True).start()
    return _jobs[job_id]


def running_job(label_prefix: str = "") -> dict | None:
    for j in _jobs.values():
        if j["state"] in ("queued", "running") and j["label"].startswith(label_prefix):
            return j
    return None


# ---------------------------------------------------------------- models
class StartTask(BaseModel):
    book: str
    workers: int = 3
    from_page: int | None = None
    to_page: int | None = None
    exclude: str = ""
    qps: int = 16
    serif: bool = False
    no_watermark: bool = True
    skip_clean: bool = False
    make_glossary: bool = False


class GlossarySave(BaseModel):
    content: str


class GlossaryGen(BaseModel):
    book: str
    pages: str = ""


class BuildFinal(BaseModel):
    book: str
    font: str = "serif"
    no_watermark: bool = True
    keep_original_layer: bool = False
    dry_run: bool = False


class RewriteToc(BaseModel):
    book: str
    translated: str
    toc: str = ""
    index: str = ""


class AddBookmarks(BaseModel):
    book: str
    translated: str


# ---------------------------------------------------------------- helpers
def _safe_path(base: Path, name: str) -> Path:
    p = (base / name).resolve()
    if not str(p).startswith(str(base.resolve())):
        raise HTTPException(400, "非法路径")
    return p


def _file_info(p: Path, base: Path = None) -> dict:
    base = base or p.parent
    return {"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime, "path": str(p)}


# 产物按书名归档: <书名>/<产物文件> (自动把 output/ 平铺文件移入对应书名文件夹)
BOOK_FILE_RE = re.compile(r"^(?P<base>.+?)(\.no_watermark)?\.zh\.(?:mono|dual)\.pdf$")
GLOSSARY_FILE_RE = re.compile(r"^(?P<base>.+?)\.zh\.glossary\.csv$")


def _book_base(name: str) -> str | None:
    m = BOOK_FILE_RE.match(name) or GLOSSARY_FILE_RE.match(name)
    return m.group("base") if m else None


def organize_output():
    """把 output/ 平铺的产物移入 output/<书名>/ 文件夹(幂等, 可反复调用)"""
    if not OUTPUT.exists():
        return
    for p in list(OUTPUT.iterdir()):
        if not p.is_file():
            continue
        base = _book_base(p.name)
        if not base:
            continue  # 无法归属的文件(如 目录_中英对照.pdf)留在根目录
        dest_dir = OUTPUT / base
        if p.parent == dest_dir:
            continue
        dest_dir.mkdir(exist_ok=True)
        try:
            p.replace(dest_dir / p.name)
        except OSError:
            pass


# ---------------------------------------------------------------- books
@app.get("/api/books")
def list_books():
    books = []
    if BOOKS.exists():
        for p in sorted(BOOKS.glob("*.pdf")):
            info = _file_info(p)
            info["pages"] = None
            try:
                import pymupdf
                doc = pymupdf.open(p)
                info["pages"] = len(doc)
                doc.close()
            except Exception:
                pass
            books.append(info)

    # 已完成的产物: 书名 -> 译文PDF (产物已按 output/<书名>/ 归档, rglob 查找)
    done = {}
    if OUTPUT.exists():
        for p in OUTPUT.rglob("*zh.mono.pdf"):
            base = re.sub(r"(\.no_watermark)?\.zh\.mono\.pdf$", "", p.name)
            done.setdefault(base, []).append({**_file_info(p, OUTPUT), "rel": str(p.relative_to(OUTPUT))})
    for b in books:
        base = b["name"][:-4]
        b["translated"] = done.get(base, [])
    return {"books": books}


@app.get("/api/books/file")
def download_book(book: str):
    p = _safe_path(BOOKS, book)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name)


@app.delete("/api/books")
def delete_book(book: str):
    p = _safe_path(BOOKS, book)
    if not p.exists():
        raise HTTPException(404)
    if running_job("translate:") and running_job("translate:")["label"].endswith(":" + book):
        raise HTTPException(409, "该书正在翻译, 先取消任务再删除")
    p.unlink()
    return {"ok": True}


@app.delete("/api/output")
def delete_output(name: str):
    p = _safe_path(OUTPUT, name)
    if not p.exists():
        raise HTTPException(404)
    p.unlink()
    return {"ok": True}


@app.post("/api/books/upload")
async def upload_book(file: UploadFile):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "仅支持 PDF")
    BOOKS.mkdir(exist_ok=True)
    dest = BOOKS / Path(file.filename).name
    with dest.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    return _file_info(dest)


@app.get("/api/books/pages")
def book_pages(book: str):
    p = _safe_path(BOOKS, book)
    try:
        import pymupdf
        doc = pymupdf.open(p)
        valid = [i + 1 for i in range(len(doc)) if len(doc[i].get_text().strip()) >= 10]
        total = len(doc)
        doc.close()
        return {"total": total, "valid": len(valid)}
    except Exception as e:
        raise HTTPException(500, f"读取失败: {e}")


# ---------------------------------------------------------------- task
@app.get("/api/task/status")
def task_status():
    f = LOGS / "status.json"
    if not f.exists():
        return {"status": None}
    try:
        return {"status": json.loads(f.read_text()), "mtime": f.stat().st_mtime}
    except Exception:
        return {"status": None}


@app.post("/api/task/start")
def task_start(req: StartTask):
    if running_job("translate:") or running_job("glossary:"):
        raise HTTPException(409, "已有任务在运行")
    book_path = _safe_path(BOOKS, req.book)
    cmd = ["uv", "run", "scripts/parallel_translate.py", str(book_path), "--workers", str(req.workers)]
    if req.from_page:
        cmd += ["--from", str(req.from_page)]
    if req.to_page:
        cmd += ["--to", str(req.to_page)]
    if req.exclude:
        cmd += ["--exclude", req.exclude]
    if req.qps != 16:
        cmd += ["--qps", str(req.qps)]
    if req.serif:
        cmd.append("--serif")
    if req.no_watermark:
        cmd.append("--no-watermark")
    if req.skip_clean:
        cmd.append("--skip-clean")
    if req.make_glossary:
        # 先生成术语表再翻译(术语表内容进翻译缓存键, 必须先于翻译)
        global _job_seq
        with _job_lock:
            _job_seq += 1
            job_id = f"{int(time.time())}_{_job_seq}"
            _jobs[job_id] = {"id": job_id, "label": "translate:" + req.book,
                             "cmd": cmd, "state": "queued", "started": time.time(),
                             "log": str(LOGS / f"web_job_{job_id}.log")}
        steps = [["uv", "run", "scripts/make_glossary.py", str(book_path)], cmd]
        threading.Thread(target=_run_chained, args=(job_id, steps), daemon=True).start()
        return {"ok": True, "job": _jobs[job_id]}
    job = start_job("translate:" + req.book, cmd)
    return {"ok": True, "job": job}


@app.post("/api/task/cancel")
def task_cancel():
    # 杀编排器进程组(SIGTERM → SIGKILL), start_new_session 使整棵树在同一进程组
    killed = []
    j = running_job("translate:")
    pid = j.get("pid") if j else None
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if pid:
            try:
                os.killpg(pid, sig)
                if sig == signal.SIGTERM:
                    killed.append(pid)
            except Exception:
                try:
                    os.kill(pid, sig)
                    if sig == signal.SIGTERM:
                        killed.append(pid)
                except Exception:
                    pass
        if sig == signal.SIGTERM:
            time.sleep(2)
    if j:
        j["state"] = "cancelled"
    return {"ok": bool(killed), "killed": killed}


@app.post("/api/task/clear")
def task_clear():
    """清除上次任务的进度记录(仅终态允许; 运行中/detached 不允许)"""
    f = LOGS / "status.json"
    if f.exists():
        try:
            phase = json.loads(f.read_text()).get("phase")
        except Exception:
            phase = None
        if phase in ("running", "merging", "detached"):
            raise HTTPException(409, "任务仍在运行, 不能清除记录")
        f.unlink()
    return {"ok": True}


# ---------------------------------------------------------------- logs
@app.get("/api/logs")
def get_logs(name: str = "orchestrator", lines: int = 200):
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
        raise HTTPException(400, "非法日志名")
    p = _safe_path(LOGS, name)
    if not p.exists():
        return {"name": name, "content": ""}
    data = p.read_text(errors="replace").splitlines()
    return {"name": name, "content": "\n".join(data[-lines:])}


@app.get("/api/logs/list")
def list_logs():
    if not LOGS.exists():
        return {"logs": []}
    return {"logs": [p.name for p in sorted(LOGS.glob("*.log"))]}


# ---------------------------------------------------------------- glossary
@app.get("/api/glossary")
def get_glossary():
    p = PROMPTS / "book_prompt.txt"
    return {"content": p.read_text() if p.exists() else "", "exists": p.exists(), "mtime": p.stat().st_mtime if p.exists() else None}


@app.put("/api/glossary")
def save_glossary(req: GlossarySave):
    PROMPTS.mkdir(exist_ok=True)
    (PROMPTS / "book_prompt.txt").write_text(req.content)
    return {"ok": True}


@app.post("/api/glossary/generate")
def gen_glossary(req: GlossaryGen):
    if running_job("glossary:"):
        raise HTTPException(409, "术语表生成中")
    p = _safe_path(BOOKS, req.book)
    cmd = ["uv", "run", "scripts/make_glossary.py", str(p)]
    if req.pages:
        cmd += ["--pages", req.pages]
    return start_job("glossary:" + req.book, cmd)


# ---------------------------------------------------------------- output
@app.get("/api/output")
def list_output():
    organize_output()  # 顺手归档 CLI 直写 output/ 的产物
    items = []
    if OUTPUT.exists():
        for p in sorted(OUTPUT.rglob("*")):
            if p.is_file() and p.suffix in (".pdf", ".csv") and "parts" not in p.parts:
                info = _file_info(p, OUTPUT)
                info["rel"] = str(p.relative_to(OUTPUT))
                items.append(info)
    items.sort(key=lambda x: -x["mtime"])
    return {"files": items}


# ---------------------------------------------------------------- postprocess
@app.get("/api/jobs")
def list_jobs():
    return {"jobs": sorted(_jobs.values(), key=lambda j: -j["started"])}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404)
    return _jobs[job_id]


@app.post("/api/postprocess/build-final")
def post_build_final(req: BuildFinal):
    book_path = _safe_path(BOOKS, req.book)
    script = ROOT / "scripts" / "build_final.sh"
    cmd = ["bash", str(script), str(book_path), "--font", req.font]
    if req.no_watermark:
        cmd.append("--no-watermark")
    if req.keep_original_layer:
        cmd.append("--keep-original-layer")
    if req.dry_run:
        cmd.append("--dry-run")
    return start_job("post:build_final", cmd)


@app.post("/api/postprocess/rewrite-toc")
def post_rewrite_toc(req: RewriteToc):
    book_path = _safe_path(BOOKS, req.book)
    translated = _safe_path(OUTPUT, req.translated)
    cmd = ["uv", "run", "scripts/rewrite_toc_index.py", str(book_path), str(translated)]
    if req.toc:
        cmd += ["--toc", req.toc]
    if req.index:
        cmd += ["--index", req.index]
    return start_job("post:rewrite_toc", cmd)


@app.post("/api/postprocess/bookmarks")
def post_bookmarks(req: AddBookmarks):
    book_path = _safe_path(BOOKS, req.book)
    translated = _safe_path(OUTPUT, req.translated)
    return start_job("post:add_bookmarks", ["uv", "run", "scripts/add_bookmarks.py", str(book_path), str(translated)])


# ---------------------------------------------------------------- env / keys
# 自定义名称 key: API_KEY_<名称>=值 (名称限 [A-Za-z0-9_], .env 会被 shell source)
# 兼容旧格式: ZHIPU_API_KEY(_N)
KEY_RE = re.compile(r"^(API_KEY_([A-Za-z0-9_]+)|ZHIPU_API_KEY(_\d+)?)\s*=\s*(.*)$")
KEY_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _read_env_lines() -> list[str]:
    f = ROOT / ".env"
    return f.read_text().splitlines() if f.exists() else []


def _mask(secret: str) -> str:
    s = secret.strip()
    if len(s) > 12:
        return s[:4] + "…" + s[-4:]
    return "****"


def _iter_keys():
    """yield (env变量名, 显示名, 值)"""
    for line in _read_env_lines():
        m = KEY_RE.match(line.strip())
        if m and m.group(4).strip():
            var = m.group(1)
            disp = m.group(2) if m.group(2) else "兼容旧格式"
            yield var, disp, m.group(4).strip()


@app.get("/api/keys")
def list_keys():
    keys = [{"id": var, "name": disp, "masked": _mask(val)} for var, disp, val in _iter_keys()]
    return {"keys": keys, "count": len(keys)}


@app.post("/api/keys/add")
def add_key(req: dict):
    name = (req.get("name") or "").strip()
    key = (req.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "key 不能为空")
    if not KEY_NAME_RE.fullmatch(name):
        raise HTTPException(400, "名称仅限字母/数字/下划线（如 main、spare1）")
    var = f"API_KEY_{name}"
    existing = {v: k for k, _, v in _iter_keys()}
    if var in existing:
        raise HTTPException(409, f"名称 {name} 已存在")
    if key in existing.values():
        raise HTTPException(409, "该 key 已存在")
    lines = _read_env_lines()
    lines.append(f"{var}={key}")
    (ROOT / ".env").write_text("\n".join(lines) + "\n")
    return {"ok": True, "count": len(list(_iter_keys()))}


@app.delete("/api/keys/{key_id}")
def delete_key(key_id: str):
    lines = _read_env_lines()
    kept, removed = [], False
    for line in lines:
        m = KEY_RE.match(line.strip())
        if m and m.group(1) == key_id:
            removed = True
            continue
        kept.append(line)
    if not removed:
        raise HTTPException(404)
    (ROOT / ".env").write_text("\n".join(kept) + "\n")
    return {"ok": True, "count": len(list(_iter_keys()))}


@app.get("/api/env")
def env_check():
    keys = len(list(_iter_keys()))
    exclude = ""
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "EXCLUDE_PAGES":
                    exclude = v.strip()
    return {"api_keys": keys, "exclude_pages": exclude}


# ---------------------------------------------------------------- static
# 注意: 挂载顺序必须在 SPA catch-all 之前, 否则产物文件会被 index.html 拦截
if OUTPUT.exists():
    app.mount("/output-files", StaticFiles(directory=OUTPUT), name="output")

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        fp = DIST / full_path
        if full_path and fp.is_file():
            return FileResponse(fp)
        return FileResponse(DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
