# aa-crawler

抓取 [artificialanalysis.ai](https://artificialanalysis.ai/) 全站聚合榜单数据，增量写入 SQLite，附一个 Bun + TypeScript + ECharts 看板。数据来自页面的 Next.js RSC payload（parsel 解析），不需要付费 API key。

需要 Python ≥3.11、[uv](https://docs.astral.sh/uv/)、[Bun](https://bun.sh/) ≥1.2。

## 覆盖范围

| dataset | 页面 | 记录数（约） | 内容 |
| --- | --- | ---: | --- |
| `llm_models` | `/leaderboards/models` | 289 | LLM 综合智能指数、各项评测分数、价格、速度、上下文 |
| `llm_providers` | `/leaderboards/providers` | 501 | 同一模型在各 API 供应商的价格、延迟、吞吐、错误率 |
| `image_models` | `/image/models` | 202 | 文生图 / 图像编辑模型 Elo、置信区间、价格 |
| `video_models` | `/video/models` | 179 | 文/图生视频、视频编辑（含音频）Elo、价格 |
| `stt_models` | `/speech-to-text` | 68 | 语音识别模型 WER、速度、价格 |
| `tts_models` | `/text-to-speech` | 114 | 语音合成模型 Elo、延迟、价格 |
| `music_models` | `/music` | 14 | 音乐生成模型 Elo、排名 |

记录保留站点原始字段（嵌套结构），并额外带上 `_dataset`、`_key`、`_observed_at`（或 `task`，图片/视频多榜单时）。

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

## 输出

## 抓取频率

默认 **2 小时**（`INTERVAL=7200`）。

- 站点 changelog 显示评测结果几乎每天多批更新；实测两轮间隔 2 分钟就有 21 条记录变化（arena Elo 等实时指标）。
- 一次全量约 33 个请求、25 MB；2 小时约 300 MB/天。6 小时会明显放大数据滞后，1 小时的收益有限。
- 可通过 `INTERVAL` / `AA_INTERVAL` 调整。

每次运行只打印一行，便于 `nohup` 监控：

```
2026-11-23 18:47:19 | ok | 69/69 datasets | 7,174 records | +0 new | ~0 changed | -0 removed | 10.7s | next 2026-11-23 20:47:19
```

前台运行时额外显示 tqdm 页面进度条；后台自动关闭进度条，只留汇总行。失败时追加一行错误摘要。

## 快速开始

```bash
make install                                # uv sync + bun install
make once                                   # 需要代理时：PROXY=http://127.0.0.1:7890
make start                                  # 后台常驻，无需 crontab
make dashboard                              # Bun 看板，默认 :8501
```

常用命令：

```bash
make once PROXY=http://127.0.0.1:7890
make start PROXY=http://127.0.0.1:7890 INTERVAL=3600
make status / logs / stop
make dashboard PORT=8501
make export / stats / datasets
make fmt            # uv format + prettier
make typecheck      # uv tool run ty check + bun tsc
make check          # 格式检查 + 类型检查 + pytest + bun tsc
```

`make start` 使用 `nohup .venv/bin/aa-crawler daemon ... &`，PID 写入 `data/crawler.pid`；失败按 300s 起步指数退避，抓取失败不会退出。

## 看板（Bun + ECharts）

```bash
make dashboard
```

前端是 `web/` 下的 TypeScript + ECharts，后端是 Bun 内置 HTTP 服务和 `bun:sqlite`，直接只读 `data/aa.db`，没有 Python Web 依赖。

- Overview：最近运行状态、活跃记录数、每次运行的新增/变化曲线、数据集规模；点击数据集可直接打开。
- Leaderboard：任意数据集自动选中主指标与价格/速度轴；搜索、Top N、对数轴、Pareto 散点、原始表格、CSV 下载。
- Trends：按记录查看 `changes` 表中的历史变化。
- Runs：该数据集每次抓取的新增/变化/删除明细。

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
  sources.py    # pydantic Source 定义，69 个数据集
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

## 说明
