# aa-crawler

抓取 [artificialanalysis.ai](https://artificialanalysis.ai/) 榜单数据的小型爬虫。数据直接从页面的 Next.js RSC payload 中提取，无需 API key；带定时循环、SQLite 历史记录和 JSONL/CSV 导出。

## 数据覆盖

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

## 快速开始

```bash
make install            # uv sync
make once               # 抓取一次，写入 data/aa.db 和 data/export/
make start              # 后台常驻，每 6 小时抓一次（不用 crontab）
make status             # 查看后台进程
make logs               # 跟踪日志
make stop               # 停止
```

需要代理时（默认直连）：

```bash
make once PROXY=http://127.0.0.1:7890
make start PROXY=http://127.0.0.1:7890 INTERVAL=3600
```

也可以用环境变量：`AA_PROXY`、`AA_INTERVAL`、`AA_DATA_DIR`、`AA_TIMEOUT`、`AA_RETRIES`。

## 输出

- `data/aa.db` — SQLite 数据库
  - `runs`：每次抓取的时间、状态（`ok` / `partial` / `failed`）
  - `dataset_runs`：每个数据集每次抓取是否成功、记录数
  - `observations`：按 `(run_id, dataset, record_key)` 保存的完整 JSON 记录
  - `latest` 视图：每个数据集最近一次成功抓取的记录
- `data/export/<dataset>.jsonl` — 最新快照，一行一条 JSON
- `data/export/<dataset>.csv` — 最新快照的扁平化表格（嵌套字段用 `a.b` 展开，数组写成 JSON）

常用查询：

```bash
sqlite3 data/aa.db "SELECT dataset, COUNT(*) FROM latest GROUP BY dataset;"
sqlite3 data/aa.db \
  "SELECT json_extract(payload,'$.name'), json_extract(payload,'$.intelligenceIndex')
   FROM latest WHERE dataset='llm_models'
   ORDER BY json_extract(payload,'$.intelligenceIndex') DESC LIMIT 10;"
```

历史对比：

```bash
sqlite3 data/aa.db \
  "SELECT observed_at, json_extract(payload,'$.name'),
          json_extract(payload,'$.intelligenceIndex')
   FROM observations
   WHERE dataset='llm_models'
     AND json_extract(payload,'$.release.slug')='gpt-6-2-astra'
   ORDER BY observed_at;"
```

## 命令

```bash
uv run aa-crawler once     [--proxy URL] [--data-dir DIR]
uv run aa-crawler daemon   [--interval SECONDS] [--jitter 0.1] [--proxy URL]
uv run aa-crawler export   [--data-dir DIR]
uv run aa-crawler stats
uv run aa-crawler datasets
```

`make start` 等价于 `nohup aa-crawler daemon ... &`，PID 写入 `data/crawler.pid`。抓取失败时自动退避重试，不会退出；成功间隔默认 6 小时（带 ±10% 抖动）。

## 开发

```bash
make test
make lint
make fmt
```

结构：

```
src/aa_crawler/
  config.py     # 配置与默认值
  fetch.py      # HTTP 客户端、重试、代理
  rsc.py        # Next.js flight payload 解析
  sources.py    # 数据集定义与记录键
  store.py      # SQLite、latest 视图、JSONL/CSV 导出
  crawl.py      # 单次抓取与常驻循环
  cli.py        # 命令行入口
```

新增榜单：在 `sources.py` 的 `SOURCES` 里加一条 `Source`（页面路径、payload 属性名、记录键字段）即可。

## 说明

- 数据版权归 Artificial Analysis；请低频抓取，仅用于研究与个人分析。
- 页面结构由 Next.js 服务端渲染，若站点改版导致属性名变化，抓取会报 `property ... not found`，需要更新 `sources.py`。
- `image/arena`、`video/arena` 的投票数据由客户端异步加载，不在 HTML payload 中，未纳入抓取。
