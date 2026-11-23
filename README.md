# aa-crawler

抓取 [artificialanalysis.ai](https://artificialanalysis.ai/) 全站聚合榜单数据，增量写入 SQLite，附一个 Bun + TypeScript + ECharts 看板。数据来自页面的 Next.js RSC payload（parsel 解析），不需要付费 API key。

需要 Python ≥3.11、[uv](https://docs.astral.sh/uv/)、[Bun](https://bun.sh/) ≥1.2。

## 覆盖范围

34 个页面、71 个数据集、7,216 条记录（其中 9 个 `*_slices` 数据集默认不显示在看板里）：

| 分组 | 数据集 | 内容 |
| --- | ---: | --- |
| `llm` | 16 | 语言模型主榜（289）、API endpoint（501）、模型发布（537）、评测目录、6 个行业 index、decision/chatbot/coding/search 元数据 |
| `image` | 8 | 文生图/编辑模型（202）、API endpoint（78）、两个 arena 主榜、tag、子榜切片 |
| `video` | 10 | 6 类视频任务（179）、API endpoint（35）、三个 arena 主榜、tag、子榜切片 |
| `speech` | 16 | STT 非流式/流式、TTS 主榜与分类分、TTS/S2S arena、模型家族、口音、子榜切片 |
| `music` | 4 | 人声 / 器乐 arena 与子榜切片 |
| `agents` | 3 | Chatbot、Coding Agent、Search API 榜单 |
| `hardware` | 7 | GPU 租价、数据中心容量测试、笔记本推理、**3,250 条手机端逐项测量** |
| `other` | 7 | 3D、micro-evals、站点 changelog |

完整列表：`make datasets`。

每条记录保留站点原始嵌套字段；导出文件额外带 `_dataset` / `_key` / `_first_seen` / `_last_seen` / `_last_changed`。

## 增量存储

`data/aa.db` 只保存每个 key 的**当前值**，变化另存事件表：

- `records(dataset, record_key, payload, content_hash, first_seen, last_seen, last_changed, active)`
  - 每次抓取计算规范化 JSON 的 SHA-256；未变化的记录只更新 `last_seen`，不重复存 payload。
  - 从榜单消失的记录标记 `active=0`，不会静默删除历史。
- `changes(run_id, dataset, record_key, observed_at, change, payload)`
  - 只在 `insert` / `update` / `remove` 时追加，用于趋势图。
- `runs` / `dataset_runs`：每次运行和每个数据集的新增、变化、删除、耗时、错误。
- `latest` 视图：`active=1` 的当前快照。

实测：首次全量约 28 MB；第二次抓取 0 新增 / 0 变化，数据库不增长。旧版（v1）数据库会自动改名为 `data/aa.legacy-*.db`。

## 抓取频率

默认 **2 小时**（`INTERVAL=7200`）。

- 站点 changelog 显示评测结果几乎每天多批更新；实测两轮间隔 2 分钟就有 21 条记录变化（arena Elo 等实时指标）。
- 一次全量约 34 个请求、25 MB；2 小时约 300 MB/天。6 小时会明显放大数据滞后，1 小时的收益有限。
- 可通过 `INTERVAL` / `AA_INTERVAL` 调整。

每次运行只打印一行，便于 `nohup` 监控：

```
2026-11-23 23:49:43 | ok | 71/71 datasets | 7,216 records | +40 new | ~0 changed | -0 removed | 7.7s | next 2026-11-24 01:49:43
```

前台运行时额外显示 tqdm 页面进度条；后台自动关闭进度条，只留汇总行。失败时追加一行错误摘要。

## 快速开始

```bash
make install                                # uv sync + bun install
make once                                   # 默认直连；代理可选
make start                                  # 后台常驻，无需 crontab
make dashboard                              # Bun 看板，默认 :8501
```

常用命令：

```bash
make once PROXY=http://127.0.0.1:7890       # 代理可选
make once WORKERS=8                         # 默认 4 并发
make start PROXY=http://127.0.0.1:7890 INTERVAL=3600
make status / logs / stop
make dashboard PORT=8501
make export / stats / datasets
make fmt            # uv format + prettier
make typecheck      # uv tool run ty check + bun tsc
make check          # 格式检查 + 类型检查 + pytest + bun tsc
```

直连可用（实测 4 并发约 8s/轮）；代理不是必需项，只作为网络受限时的加速/备用。`WORKERS` / `AA_WORKERS` 控制并发页面数。

`make start` 使用 `nohup .venv/bin/aa-crawler daemon ... &`，PID 写入 `data/crawler.pid`；失败按 300s 起步指数退避，抓取失败不会退出。

## 看板（Bun + ECharts）

```bash
make dashboard
```

前端是 `web/` 下的 TypeScript + ECharts，后端是 Bun 内置 HTTP 服务和 `bun:sqlite`，直接只读 `data/aa.db`，没有 Python Web 依赖。

- Overview：最近运行状态、活跃记录数、每次运行的新增/变化曲线、数据集规模；点击数据集可直接打开。
- Leaderboard：任意数据集自动选中主指标与价格/速度轴；搜索、Top N、对数轴、Pareto 散点、可排序表格、CSV 下载。
- Trends：按记录查看 `changes` 表中的历史变化。
- Runs：该数据集每次抓取的新增/变化/删除明细。
- 明暗主题切换（跟随系统初值、localStorage 记忆）、自动刷新 60s、快捷键 `/` 聚焦搜索、原始子榜开关。
- 选择的分组/数据集/Tab 会记住，刷新页面后恢复。

接口：

```
GET /api/summary
GET /api/records?dataset=llm_models
GET /api/history?dataset=llm_models&key=...
GET /api/runs?dataset=llm_models
```

`data/datasets.json` 由 Python 抓取/导出时生成，提供分组、标签和主数据集标记；缺失时看板退化为按数据库现有 dataset 展示。API 缓存 15 秒，可边抓边看。

## 数据查询

```bash
sqlite3 data/aa.db "SELECT dataset, COUNT(*) FROM latest GROUP BY dataset;"

# 智能指数 vs 输出价格 Top 10
sqlite3 data/aa.db "
SELECT json_extract(payload,'$.name'),
       json_extract(payload,'$.intelligenceIndex'),
       json_extract(payload,'$.price1mOutputTokens')
FROM latest WHERE dataset='llm_models'
ORDER BY json_extract(payload,'$.intelligenceIndex') DESC LIMIT 10;"

# 某个模型的历史变化
uv run aa-crawler history llm_models 'claude-fable-5-2/Max, Default Fallback'
```

## 结构

```
src/aa_crawler/
  config.py     # pydantic Settings + 默认频率
  sources.py    # pydantic Source 定义，71 个数据集
  fetch.py      # httpx、重试、代理
  rsc.py        # parsel 取 script → flight payload → JSON
  extract.py    # array / values / tables / path 抽取模式
  store.py      # 增量 SQLite、changes、导出、manifest
  crawl.py      # 单次抓取、tqdm、常驻循环、单行汇总
  cli.py        # click 命令

web/
  src/server.ts # Bun.serve + bun:sqlite，只读 API
  src/app.ts    # TypeScript 前端、ECharts
  src/index.html
  src/style.css
  package.json  # echarts / typescript / prettier
```

工具链：Python 用 `uv format` 与 `uv tool run ty check`；前端用 Bun 安装依赖、`bun run check`（tsc）与 Prettier。

## 限制

- 未逐页抓取 2,435 个模型详情页和 57 个 provider 详情页：它们展示的指标已汇总在榜单与 endpoint 数据中，逐页抓取会让每轮请求量放大两个数量级。
- arena 页面按 tag/口音/语言切分的 201 张子榜表作为 `*_slices` 原始数据集入库，默认不显示在看板列表中；投票 UI（`/image/arena`、`/video/arena` 等）本身不下发数据。
- 官方 `/api/v2` 是付费 API；本项目抓公开页面，若站点改版会报 `property ... not found`，更新 `sources.py` 即可。
- 数据版权归 Artificial Analysis，请低频抓取，仅用于研究与个人分析。
