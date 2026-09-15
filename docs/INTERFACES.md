# 接口文档（面向前端集成与后续维护）

> 已有基于本文档实现的完整 Web 界面（FastAPI 壳 + Vue3 前端），见 **docs/WEB.md**。
> 其 REST API 是本文档三件事（启动/轮询/取产物）的具体封装。

> 本文档描述 PDF 翻译工具的全部对外接口。前端（Web UI / 桌面壳）只需关心三件事：
> **① 如何启动任务**（调脚本，子进程方式）**② 如何获知进度**（轮询 `logs/status.json`）
> **③ 如何取产物**（`output/` 目录的文件命名规则）。

## 1. 系统架构与数据流

```
前端/CLI
  │ subprocess 调用
  ▼
scripts/parallel_translate.py ──────► logs/status.json   ← 前端轮询(每30s刷新)
  │ 按有效页拆 N 片, 每片一个子进程
  ▼
pdf2zh_next (BabelDOC 内核) ──► 智谱 API (glm-4-flash, OpenAI 兼容)
  │ 版面识别(ONNX) → 段落组装 → LLM 翻译 → 排版缩放 → 重绘PDF
  ▼
output/parts/partN/*.pdf ──► 自动合并+补页 ──► output/<书名>.zh.mono.pdf
  │                                          (前端展示/下载的最终产物)
  ▼ 后处理(可选, 独立脚本)
build_final.sh(字体/水印/原文层) · rewrite_toc_index.py(目录中文化) · add_bookmarks.py(书签)
```

**关键事实**
- 翻译缓存位于 `~/.cache/babeldoc/cache.v1.db`（sqlite）。相同段落+相同提示词不会重复计费/耗时，
  重跑 = 断点续传。**提示词或术语表变化会使缓存失效**（触发真实 API 调用）
- 翻译任务是长时的（数百页 = 数十分钟），前端必须按"启动 → 轮询 → 完成取文件"的异步模型设计
- 所有脚本都应在项目根目录以 `uv run scripts/xxx.py` 方式调用（自动激活 .venv 与 .env）

## 2. 前端集成速查

| 步骤 | 做法 |
|---|---|
| 启动翻译任务 | `uv run scripts/parallel_translate.py <pdf> --workers N` （后台长进程，建议 nohup/setsid） |
| 轮询进度 | 读 `logs/status.json`（每 30s 更新，schema 见 §3） |
| 判断完成 | `phase == "done"` 且 `output` 字段非空 |
| 展示进度条 | `total.percent` / `total.eta_seconds` / 各 worker 明细 |
| 失败处理 | `phase == "failed"` → 展示哪些 worker 失败；修复后**重跑同一命令**即可断点续传 |
| 交付产物 | `output` 字段指向的 PDF（751 页示例: 与原书页码对齐） |
| 取消任务 | kill 编排器进程树（注意先杀子进程，避免残留 pdf2zh 子进程） |

## 3. status.json 规范（parallel_translate.py 产出）

路径: `logs/status.json`，每 30 秒覆写一次，任务结束时写入终态。

```json
{
 "book": "books/xxx.pdf",
 "phase": "running",                    // parsing阶段包含在running内; running|merging|done|failed|detached
 "started_at": "2026-09-15T11:00:00",
 "updated_at": "2026-09-15T11:30:00",
 "workers": [                            // 各分片实时状态
   {"id": 0, "state": "done",    "pages_done": 244, "pages_total": 244},
   {"id": 1, "state": "running", "pages_done": 120, "pages_total": 243,
    "elapsed_sec": 600, "eta_sec": 300},
   {"id": 2, "state": "parsing", "pages_total": 243}
 ],
 "total": {
   "pages": 730, "done": 364, "percent": 49.9,
   "speed_pages_per_min": 11.2, "eta_seconds": 1740
 },
 "output": null                          // phase=done 时为最终PDF绝对路径
}
```

**worker.state 取值**: `parsing`（版面解析中，CPU 密集，尚无页码进度）| `running` |
`done` | `failed`
**phase 取值**: `running` | `merging`（分片齐了正在合并）| `done` | `failed` |
`detached`（用户 Ctrl+C 退出监控，后台仍在跑，此时 workers/total 为空）

## 4. 脚本接口明细

### 4.1 scripts/parallel_translate.py — 并行翻译编排器（核心）

```bash
uv run scripts/parallel_translate.py [书.pdf] [选项]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--workers N` | 3 | 进程数。**N ≤ 可用 API key 数**，每进程 16 QPS |
| `--from N` / `--to N` | 1 / ∞ | 页码区间 |
| `--exclude "7-12"` | 空 | 排除页（空白/扫描页总是自动排除） |
| `--qps N` | 16 | 每进程请求频率 |
| `--serif` / `--no-watermark` / `--skip-clean` | 关 | 排版选项（体积影响见 §6） |
| `--custom-system-prompt S` | prompts/book_prompt.txt | 覆盖术语表提示词 |

- **输入**: 有文字层的 PDF（无文字层页自动跳过）
- **输出**: `output/parts/partN/*.pdf`（分片）→ `output/<书名>.zh.mono.pdf`（合并+补页成品）；
  `logs/partN.log`（明细日志）；`logs/status.json`（进度）
- **退出码**: 0=全部完成并合并成功；非 0=有 worker 失败（已完成的分片保留，重跑续传）
- **合并语义**: 分片按 worker 轮转分配，合并按 `chunk_lists` 精确映射到原书页码，
  非有效页（空白/排除页）以原书页面补齐 → **成品页数=原书页数**（含 `.no_watermark` 后缀变体，见 §6）

### 4.2 scripts/build_final.sh — 最终版构建（重排版，交互/参数两用）

译文已在缓存时，仅重排版不改译文。**给终端用户用的推荐入口**。

```bash
./scripts/build_final.sh                       # 交互菜单
./scripts/build_final.sh 书.pdf --font serif --no-watermark --dry-run
```

| 选项 | 取值 | 效果 |
|---|---|---|
| `--font` | `serif`(宋体/书籍风) \| `sans`(黑体/屏显) | 正文字体 |
| `--no-watermark` / `--keep-watermark` | 开关 | 去除 funstory 署名 |
| `--keep-original-layer` | 开关 | 保留英文原文层（可搜索/复制）。**体积 ×12**（751 页实测 50MB→540MB） |
| `--dry-run` | — | 只打印将执行的完整命令，不运行 |

产物: `output/<书名>.zh.mono.pdf`（开 `--no-watermark` 时文件名带 `.no_watermark` 中缀，
这是 BabelDOC 的行为，前端找文件要匹配 `*zh.mono.pdf` 通配）。

### 4.3 scripts/translate.sh — 单进程翻译（简单场景）

```bash
./scripts/translate.sh [书.pdf] [pdf2zh_next 参数透传...]
```
自动: 探测有效页 + 应用 `EXCLUDE_PAGES` + 加载术语表。固定 16 QPS 单 key。
产物同名规则同上。适合小文件/快速验证；长书用 4.1。

### 4.4 scripts/make_glossary.py — 译前术语表生成

```bash
uv run scripts/make_glossary.py books/X.pdf [--pages 3-15] [--out 路径]
```
- 读前言/目录/摘要页 → LLM 提炼 30~50 条「英文=中文」术语 + 风格规则
- **输出**: `prompts/book_prompt.txt`（两个翻译脚本自动读取；换书前必须重新生成）
- 提示词内容会进入翻译缓存键 → 生成后务必用同一份提示词跑完整本书

### 4.5 scripts/rewrite_toc_index.py — 目录/索引区域重写

```bash
uv run scripts/rewrite_toc_index.py books/原书.pdf output/译文.pdf [--toc 7-18] [--index 717-750]
```
- 解决 BabelDOC 对"表格型文本"（标题列+页码列）粘连的问题：按视觉行聚类 + 双栏切分，
  LLM 只翻标题，按原坐标重绘，页码/缩进/栏位保留，**原位替换**译文 PDF 对应页
- 页码自动探测（书签 Contents/Index + 行尾页码占比统计），探测失败手动传参
- 内置 429 指数退避（5s→160s）；替换后保持书签与页数不变

### 4.6 scripts/add_bookmarks.py — 中文书签

```bash
uv run scripts/add_bookmarks.py books/原书.pdf output/译文.pdf
```
复制原书 outline 结构（页码天然与补页后的译文对齐），标题批量 LLM 翻译。
注意: BabelDOC 自带 TOC 迁移，很多情况下产物已有中文书签——**先 `get_toc()` 检查再决定是否需要跑**。

### 4.7 scripts/restore_pages.py — 补回排除页

```bash
uv run scripts/restore_pages.py books/原书.pdf output/译文.pdf --exclude 7-12
```
仅适用于"译文页序=有效页升序"的产物（translate.sh 单进程结果）。parallel_translate.py
的合并已内置，无需再跑。`--exclude` 必须与翻译时一致，否则页数校验会报错拒绝执行。

### 4.8 scripts/make_toc_pdf.py — 中英对照目录附件（可选）

```bash
uv run scripts/make_toc_pdf.py books/X.pdf [--pages 7-12] [--out 路径]
```
独立生成 `目录_中英对照.pdf` 附件（不动正文）。v2 逻辑已修（4 字段解析/页码空格清洗），
输出尚未人工验收。

## 5. 配置与产物清单

### .env（gitignore，模板见 .env.example）

| 变量 | 必填 | 说明 |
|---|---|---|
| `ZHIPU_API_KEY` | 是 | 智谱 key；`_2`..`_N` 为可选额外 key，编排器自动发现并轮换 |
| `EXCLUDE_PAGES` | 否 | `translate.sh` 的自动页探测排除项（如目录页 `7-12`） |

### 产物命名规则（前端找文件用）

| 文件 | 含义 |
|---|---|
| `output/<书名>.zh.mono.pdf` | 纯中文译文（最终交付物） |
| `output/<书名>.no_watermark.zh.mono.pdf` | 同上（去水印构建的产物，BabelDOC 自动加中缀） |
| `output/<书名>.zh.dual.pdf` | 双语对照版（默认关闭，需要时去掉 `--no-dual`） |
| `output/<书名>.zh.glossary.csv` | 自动提取的术语表 |
| `output/parts/partN/…` | 分片中间产物（合并后可删） |
| `logs/status.json` · `logs/partN.log` · `logs/orchestrator.log` | 进度状态 / worker 明细 / 监控输出 |

## 6. 外部依赖接口

### pdf2zh_next CLI（本项目用到的子集）

`--pages "1,3-5,10-"` · `--zhipu --zhipu-model M --zhipu-api-key K` ·
`--qps N --pool-max-workers N` · `--only-include-translated-page`（分片合并的前提）·
`--no-dual` · `--formular-font-pattern "(?!x)x"`（修目录页码乱码，勿删）·
`--split-short-lines` · `--min-text-length N` · `--ignore-cache` ·
`--custom-system-prompt S` · `--primary-font-family serif|sans-serif` ·
`--watermark-output-mode no_watermark` · `--skip-clean` · `--output DIR`
完整列表: `uv run pdf2zh_next --help`

### 智谱 API（OpenAI 兼容）

- `POST https://open.bigmodel.cn/api/paas/v4/chat/completions`，`Authorization: Bearer <key>`
- 模型: `glm-4-flash`（免费 ~3.9s/req，全书翻译用）/ `glm-4.5-flash`、`glm-4.7-flash`
  （免费思考型 33~105s/req，精修用；可传 `{"thinking":{"type":"disabled"}}` 但输出易跑偏）
- 限流: **账号级为主**（同 IP 多 key 吞吐 ~1.5×/key 递增）；429 需指数退避重试
  （rewrite_toc_index.py 已内置，可复用该模式）

### BabelDOC 排版引擎要点（源码 `…/babeldoc/format/pdf/document_il/`）

版面识别（DocLayout-YOLO ONNX，只译正文区域）→ 段落组装（y 聚类+分栏，表格型文本
会粘连 → 4.5 的动因）→ 逐段 optimal_scale 缩放并**取全文众数统一字号** → 重绘+字体子集。
已知局限: 目录/索引粘连（4.5 解决）、`--split-short-lines` 仅部分缓解。

### BabelDOC 缓存

`~/.cache/babeldoc/cache.v1.db`。清缓存=删文件。**缓存键含提示词**——任何 prompt/术语表
变更都会造成大规模真实 API 重译（计费/耗时/限流风险）。
