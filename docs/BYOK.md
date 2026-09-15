# BYOK：用户自带 API Key（Bring Your Own Key）

> 本项目**不提供、不转售、不代理任何 LLM API 服务**。翻译所需的 API key 由使用者
> 自行注册、自行配置、自行承担费用与服务条款。项目代码只负责"用你给的 key 去调用"。

## 1. 工作方式

- 所有 key 配置在**本地** `.env` 文件（已 gitignore，永不出机器），或通过 Web 界面环境检查确认
- 翻译进程（pdf2zh_next）直接持有 key 向服务商发请求，本项目服务器/仓库**不经手、不存储、不转发**任何 key
- 换服务商 = 换 pdf2zh_next 的引擎参数（20+ 引擎：deepl/ollama/siliconflow…），改法见 docs/INTERFACES.md §6

## 2. 多 key 轮换机制（说明）

`.env` 中按命名约定放置多个 key：

```bash
ZHIPU_API_KEY=key1          # 必填, 主 key
ZHIPU_API_KEY_2=key2        # 可选
ZHIPU_API_KEY_3=key3        # 可选, 以此类推 (_4, _5 ...)
```

编排器 `scripts/parallel_translate.py` 的调度规则：

1. **自动发现**：启动时扫描 `.env` 中所有 `ZHIPU_API_KEY(_N)` 变量，得 key 池。
   Web 界面「设置」页可增删 key（脱敏显示，写回 .env 时其余配置行原样保留）
2. **worker : key = 1 : 1**：N 个并行进程按顺序绑定 N 个 key（第 i 个 worker 用第 i 个 key）
3. **进程内并发**：每个进程对**自己绑定的单个 key** 以 16 QPS 并发请求（`--qps` 可调）
4. **无跨进程共享**：一个 key 不会被两个 worker 同时使用，避免同账号自我竞争
5. **横向扩展**：吞吐随 key 数量近似 1.5×/key 递增

```
.env 有 3 个 key  →  建议 --workers 3
.env 只有 1 个 key →  --workers 大于 1 无收益（同 key 多进程 ≈ 单进程速度）
```

## 3. 合规提示（使用者必读）

- 多 key 轮换的前提是**你拥有这些 key**。请确认你的服务商条款允许单账号多 key 与所述并发量；
  若服务商限制并发/限制规避限流，由使用者自行承担责任
- key 等同账户凭证：不要提交到 git（本仓库 .gitignore 已排除 .env）、不要写进文档截图
- 在公共/共享环境部署时注意 .env 的文件权限（`chmod 600 .env`）
