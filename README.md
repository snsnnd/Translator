# PDF 书籍翻译器（英文 → 中文，保留排版）

基于 [pdf2zh-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next)（BabelDOC 内核）的批量书籍翻译工具。已在真实书籍上验证：
**730 页技术书 1 小时 22 分钟翻完，成本 ¥0（免费模型），排版/公式/图表坐标保留，专业术语准确**。

> key 由使用者自行配置并承担费用与条款，详见 **docs/BYOK.md**。
> **License**: [AGPL-3.0](LICENSE)（依赖的 pdf2zh-next/BabelDOC/PyMuPDF 均为 AGPL，
> 二次开发与网络服务需遵守同款开源义务，版权声明见 [NOTICE](NOTICE)）

## 目录结构

```
Translator/
├── README.md                 # 本文件
├── docs/
│   ├── INTERFACES.md         # 接口文档: 脚本接口/status.json规范/产物命名/外部依赖(面向前端集成)
│   ├── WEB.md                # Web 界面文档(架构/页面功能/API 参考/已知限制)
│   ├── BYOK.md               # 用户自带 API Key 说明 + 多 key 轮换机制
│   └── PACKAGE.md            # 打包分发指南(便携 zip / 小白三步安装)
├── scripts/
│   ├── parallel_translate.py # 多进程并行编排器(进度/ETA/自动合并) ← 翻译主力
│   ├── build_final.sh        # 最终版构建: 交互选 字体/水印/原文层(体积12倍差)
│   ├── translate.sh          # 单进程翻译(简单场景/断点续传)
│   ├── make_glossary.py      # 译前: 读前言/目录自动生成全书术语表
│   ├── rewrite_toc_index.py  # 目录/索引区域重写(中文进PDF正文)
│   ├── add_bookmarks.py      # 中文书签(原书outline结构)
│   ├── restore_pages.py      # 补回排除页(页码对齐原书)
│   └── make_toc_pdf.py       # 可选: 生成中英对照目录PDF附件
├── prompts/
│   └── book_prompt.txt       # 当前书的术语表(make_glossary.py 生成, 按书覆盖)
├── web/                      # Web 界面 (FastAPI 壳 + Vue3 前端, 完整文档见 docs/WEB.md)
├── launch/                   # 一键启动器: Windows bat / macOS-Linux sh / .desktop 模板
├── books/                    # 待翻译的源 PDF(gitignore)
├── output/                   # 译文产物(gitignore)
├── LICENSE                   # AGPL-3.0 全文
├── NOTICE                    # 第三方组件版权声明
├── .env                      # 密钥与配置(含密钥, 严禁提交)
├── .env.example              # 配置模板
└── pyproject.toml            # uv 环境, python 3.10-3.12
```

## 快速开始

```bash
# 0) 环境(首次)
uv sync                          # 安装依赖(需先装 uv)

# 1) 配置密钥: 复制 .env.example 为 .env, 填入智谱 key
#    https://open.bigmodel.cn 注册即送, glm-4-flash 免费无配额上限
cp .env.example .env && vim .env

# 2) 把书放进 books/, 然后一条命令全书翻译
uv run scripts/parallel_translate.py books/你的书.pdf --workers 5
#    完成: output/<书名>.zh.mono.pdf (纯中文版, 自动合并)

# 可选: 先生成该书专属术语表(提升专业名词一致性)
uv run scripts/make_glossary.py books/你的书.pdf
```

## 常用命令

| 场景 | 命令 |
|---|---|
| **Web 界面（推荐）** | Windows 双击 `launch/启动翻译器.bat`；或 `uv run web/server/main.py` → http://localhost:8000 (文档见 docs/WEB.md) |
| 全书并行翻译（推荐） | `uv run scripts/parallel_translate.py books/X.pdf --workers 5` |
| 只翻部分页 | `uv run scripts/parallel_translate.py books/X.pdf --from 50 --to 200` |
| 排除某些页(如目录) | `.env` 里设 `EXCLUDE_PAGES=7-12` 或 `--exclude 7-12` |
| 单进程翻译/续传 | `./scripts/translate.sh books/X.pdf --pages 100-200` |
| 查看运行进度 | 读 `logs/status.json`（结构化，前端可轮询）或 `tail -f logs/orchestrator.log` |
| 生成术语表 | `uv run scripts/make_glossary.py books/X.pdf [--pages 3-15]` |
| 重排版(选字体/水印/原文层) | `./scripts/build_final.sh` (交互菜单, 支持 --dry-run) |
| 中文书签 | `uv run scripts/add_bookmarks.py books/X.pdf output/X译文.pdf` |
| 补页对齐 | `uv run scripts/restore_pages.py books/X.pdf output/X译文.pdf --exclude 7-12` |
| 目录/索引中文化 | `uv run scripts/rewrite_toc_index.py books/X.pdf output/X译文.pdf` |
| 中英对照目录 | `uv run scripts/make_toc_pdf.py books/X.pdf --pages 7-12` |

**前端集成**: 启动 → 轮询 `logs/status.json`（schema 见 docs/INTERFACES.md §3）→ 取 `output` 产物。
详细接口说明见 **docs/INTERFACES.md**。

## 核心结论速览

- **模型选型**：`glm-4-flash` 全书翻译最优（3.9s/请求，免费，术语准）；4.5/4.7-flash 是思考型模型（33~105s/请求），只适合少量精修
- **限流是账号级**（带少量 IP 共享成分）：单 key 16 并发 ≈ 12.8 页/分；多 key 轮换到多进程，吞吐约 1.5×/key 递增
- **排版两个坑已修复**：目录页码变红色 `<code>` 乱码 → `--formular-font-pattern "(?!x)x"`；空白扫描页导致中断 → 自动探测跳过
- **目录页建议不翻**：BabelDOC 对目录"短行+页码"的段落合并无法根治，跳过保留英文原版最稳

## 维护与扩展

- **换翻译引擎**：pdf2zh_next 内置 20+ 引擎（deepl/ollama/siliconflow...），改脚本里 `--zhipu` 段即可，接口文档有映射表
- **加新语言**：所有 prompt 里 `English to Simplified Chinese` 改目标语言 + 术语表格式即可
- **适配扫描版书**：当前自动跳过无文字层页面；整本扫描的书需先 `ocrmypdf -l eng 书.pdf 书_ocr.pdf` 预处理
- **修改脚本后**：`bash -n scripts/translate.sh` 验证 shell 语法；`uv run python -c "import ast; ast.parse(open('scripts/X.py').read())"` 验证 Python

## 免责声明

- 本工具按"现状"提供，**不含任何担保**；作者不对使用本工具产生的任何后果承担责任
- 使用者须确保对所翻译的文件**拥有合法权利**（自有版权、公有领域、获得授权或属于当地法律允许的私人复制范围）。**未经权利人许可翻译受版权保护的作品、分发原文或译本，可能构成侵权**，责任由使用者自行承担
- 本工具不内置、不分发任何书籍内容；仓库不含任何受版权保护的文本样本
- 本工具不提供 LLM API 服务。使用者配置的 API key 及其调用产生的费用、数据与合规责任，由使用者与其 API 服务商之间解决
- 本项目基于 AGPL-3.0 授权。分发本程序或以本程序为基础提供网络服务时，须遵守 AGPL-3.0 的开源义务（提供完整对应源码、保留版权与许可声明）

## License

[AGPL-3.0](LICENSE) · 第三方组件版权声明见 [NOTICE](NOTICE)
