# Web 界面文档

> 本地单用户 Web UI。设计原则：**零侵入**——不修改任何现有翻译脚本，
> 只通过 ①subprocess 启动 ②读 `logs/status.json` ③托管 `output/` 三种方式集成
> （对应 docs/INTERFACES.md 的前端集成模型）。

## 1. 快速开始

```bash
# 日常启动 (前端已构建好, 无需 Node)
uv run web/server/main.py        # → http://localhost:8000

# 改了前端代码后重新构建 (需要 Node 18+, 本机装在 ~/.local/opt/node-*)
cd web && npm install && npm run build
```

- 前后端联调模式：`cd web && npm run dev`（Vite 跑 5173，已配置 `/api`、`/output-files` 代理到 8000）
- 默认只监听 127.0.0.1；要局域网访问改 `web/server/main.py` 末尾 `uvicorn.run(..., host="0.0.0.0")`（注意无鉴权，勿暴露公网）

## 2. 架构与数据流

```
浏览器 (Vue 3 SPA, web/dist 由 FastAPI 托管)
   │ HTTP /api/*
   ▼
web/server/main.py (FastAPI 壳, ~400行)
   ├─ subprocess (start_new_session) 启动 scripts/*.py 或 build_final.sh
   ├─ 读 logs/status.json、logs/*.log、prompts/book_prompt.txt 转成 JSON API
   └─ StaticFiles 挂载 output/ → /output-files (PDF 预览/下载)
   ▼
现有脚本 (零改动): parallel_translate.py / make_glossary.py / build_final.sh / ...
```

### 关键实现说明

| 机制 | 做法 | 原因 |
|---|---|---|
| 长任务模型 | 启动后立即返回，前端轮询 `/api/task/status`（3s） | 数百页翻译是几十分钟级长进程（INTERFACES.md §1） |
| 术语表先行 | 勾选"自动生成"时，job 内先跑 make_glossary.py 再跑翻译（链式，任一步失败即止） | 术语表内容进翻译缓存键，必须先于翻译定稿 |
| 取消任务 | 对编排器 pid 发 `killpg(SIGTERM → 2s → SIGKILL)` | start_new_session 使整棵进程树同组；先杀子进程再杀父进程，防残留 |
| 删除保护 | 源书正在翻译时 DELETE 返回 409 | 防止删掉运行中任务的输入 |
| status.json 生命周期 | `running/merging/detached` 视为活动任务；`done/failed` 只是"上次记录"，可清除 | 文件是单槽终态驻留，不做区分会误显示为进行中 |
| SPA 路由 | catch-all 返回 index.html | **注意：必须注册在 `/output-files` 挂载之后**，否则产物请求被 index.html 拦截（已踩坑） |
| 路径安全 | 所有按名取文件的端点过 `_safe_path`（resolve 后校验前缀） | 防路径穿越 |

## 3. 页面功能

| 页面 | 路由 | 功能 |
|---|---|---|
| 书架 | `/` | 扫描 `books/*.pdf`（页数/大小/已翻译标记）；拖拽或点击上传；已翻译的书：翻译按钮禁用 + 「下载▾」菜单（原文/译文/无水印版/双语版）+ 重翻入口；🗑 删除源书（译文产物保留） |
| 新建翻译 | `/new` | 选书（显示总页数/有效页数）；workers、QPS、页码范围、排除页；排版选项（宋体/去水印/保留原文层含体积警告）；术语表查看/编辑/自动生成；启动后跳进度页 |
| 任务进度 | `/progress` | 总进度（百分比/页数/速度/ETA）；worker 分片矩阵（parsing/running/done/failed 四色卡片+单片进度）；实时日志（orchestrator/partN.log 切换、自动滚动）；取消任务；终态记录可清除 |
| 产物 | `/output` | 列出 `output/` 全部成品（自动分类标签：纯中文/双语/术语表/目录附件）；PDF 在线预览（iframe）；下载；🗑 删除 |
| 工具箱 | `/toolbox` | 重排版构建 build_final.sh（字体/水印/原文层/dry-run 预览命令）；目录索引中文化 rewrite_toc_index.py（页码可留空自动探测）；中文书签 add_bookmarks.py；最近任务历史 |
| 设置 | `/settings` | **API key 管理**：添加/删除（脱敏显示，只写本地 .env）、数量与吞吐提示；EXCLUDE_PAGES；缓存说明 |

## 4. API 参考

### 任务
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/task/start` | body: `{book, workers, from_page?, to_page?, exclude?, qps?, serif?, no_watermark?, skip_clean?, make_glossary?}`；已有任务时 409 |
| GET | `/api/task/status` | 返回 `{status, mtime}`，status 为 status.json 原文或 null |
| POST | `/api/task/cancel` | 杀编排器进程组；分片保留可断点续传 |
| POST | `/api/task/clear` | 清除上次记录；活动任务（running/merging/detached）时 409 |

### 书与术语表
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/books` | books/ 列表（含 pages 页数、translated 已匹配的 `*zh.mono.pdf` 产物） |
| GET | `/api/books/pages?book=` | `{total, valid}`（valid = 有文字层页数，≥10 字符） |
| GET | `/api/books/file?book=` | 下载原文 PDF |
| POST | `/api/books/upload` | multipart `file`，仅 PDF |
| DELETE | `/api/books?book=` | 删源书（翻译中 409） |
| GET/PUT | `/api/glossary` | 读/写 `prompts/book_prompt.txt` |
| POST | `/api/glossary/generate` | body: `{book, pages?}`，后台 job |

### 日志 / 产物 / 作业
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/logs/list` | logs/ 下 *.log 文件名 |
| GET | `/api/logs?name=&lines=` | tail N 行（name 白名单校验） |
| GET | `/api/output` | output/ 产物列表（rglob，排除 parts/ 中间产物） |
| GET | `/api/output` 下文件 | 预览/下载走 `/output-files/<encodeURIComponent(name)>` 静态挂载 |
| DELETE | `/api/output?name=` | 删产物 |
| POST | `/api/postprocess/build-final` | `{book, font: serif|sans, no_watermark, keep_original_layer, dry_run}` |
| POST | `/api/postprocess/rewrite-toc` | `{book, translated, toc?, index?}`（页码空则脚本自动探测） |
| POST | `/api/postprocess/bookmarks` | `{book, translated}` |
| GET | `/api/jobs` · `/api/jobs/{id}` | 所有后台作业（翻译/术语表/后处理统一走 job runner） |
| GET | `/api/keys` | key 列表（**始终脱敏**：前4…后4）+ 数量 |
| POST | `/api/keys/add` | body: `{key}`，追加一个 key；重复 409 |
| DELETE | `/api/keys/{id}` | 删除指定 key（如 ZHIPU_API_KEY_3），剩余 key 顺位重排 |
| GET | `/api/env` | `{api_keys, exclude_pages}`（key 只返回数量） |

### job 状态机
`queued → running → done | failed`（返回码非 0 即 failed）；多步链式 job 失败时带 `failed_step`。日志落在 `logs/web_job_<id>.log`，进度页/工具箱均可查看。

## 5. 前端工程

```
web/
├── server/main.py        # FastAPI 后端壳
├── src/
│   ├── main.js           # 路由注册
│   ├── api/index.js      # 后端 API 封装 (唯一 fetch 入口)
│   ├── style.css         # Tailwind 4 入口 + 滚动条样式
│   ├── App.vue           # 侧边栏布局
│   ├── components/PhaseBadge.vue   # 状态徽章 (worker/phase/job 通用)
│   └── views/            # Books / NewTask / Progress / Output / Toolbox / Settings
├── dist/                 # 构建产物 (gitignore, FastAPI 托管)
└── vite.config.js        # Tailwind 插件 + dev 代理
```

技术栈：Vue 3（Composition API）+ Vue Router + Tailwind CSS 4 + Vite 6。
无状态管理库——各页面自行轮询；无 UI 组件库——原生元素 + Tailwind。

## 6. 已知限制

- **单任务槽**：与 status.json 的单槽模型一致，同一时刻只允许一个翻译任务
- **双语对照版**：parallel_translate.py 硬编码 `--no-dual`，界面不提供该选项（需要时用单进程 translate.sh 路径）
- **进度粒度 30s**：status.json 由编排器每 30s 覆写，前端 3s 轮询不会更细
- **无鉴权**：设计为 localhost 单用户工具；如暴露局域网需自行加认证
- **重跑同一本书**：需在「新建翻译」里用原参数（排除页等），缓存才最大命中
