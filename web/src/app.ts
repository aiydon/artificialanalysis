import * as echarts from "echarts";
import type { EChartsType } from "echarts";

type Tab = "leaderboard" | "trends" | "runs";

interface DatasetMeta {
  dataset: string;
  group: string;
  label: string;
  primary: boolean;
  dashboard: boolean;
  count: number;
  last_changed: string | null;
}

interface Totals {
  pages?: number;
  datasets_ok?: number;
  records?: number;
  inserted?: number;
  updated?: number;
  unchanged?: number;
  removed?: number;
}

interface Run {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  totals: Totals | null;
}

interface Summary {
  generated_at: string | null;
  last_run: Run | null;
  runs: Run[];
  datasets: DatasetMeta[];
  active: number;
}

interface RecordRow {
  key: string;
  payload: Record<string, unknown>;
  first_seen: string;
  last_seen: string;
  last_changed: string;
}

interface RecordsResponse {
  dataset: string;
  records: RecordRow[];
}

interface Change {
  observed_at: string;
  change: string;
  payload: Record<string, unknown>;
}

interface HistoryResponse {
  dataset: string;
  key: string;
  changes: Change[];
}

interface DatasetRun {
  run_id: number;
  started_at: string;
  status: string;
  records: number;
  inserted: number;
  updated: number;
  unchanged: number;
  removed: number;
  duration_ms: number;
  error: string | null;
}

interface RunsResponse {
  dataset: string;
  runs: DatasetRun[];
}

type FlatRow = Record<string, unknown> & { _key: string; _last_changed: string };

const Y_PRIORITY = [
  "intelligenceIndex",
  "weightedIndex",
  "headlineValue",
  "elo",
  "qualityElo",
  "aaSearchQualityIndex",
  "bbaScore",
  "outputSpeed",
  "performance.outputSpeed",
  "performance.medianGenerationTimeSeconds",
  "value",
];
const X_PRIORITY = [
  "price",
  "price1mOutputTokens",
  "price1mInputTokens",
  "pricing.price1mOutputTokens",
  "pricing.price1mInputTokens",
  "pricePer1kImages",
  "pricePerMinute",
  "pricePer1mCharacters",
  "pricePerHourInput",
  "pricePer1kMinutes",
  "costPerTask.total",
  "timeToFirstToken",
  "timeToFirstAudioSeconds",
  "performance.timeToFirstToken",
  "appearances",
];
const NAME_PRIORITY = [
  "name",
  "shortName",
  "label",
  "modelName",
  "agentName",
  "providerName",
  "deviceKey",
  "modelId",
  "modelKey",
  "systemKey",
  "key",
];
const CREATOR_PRIORITY = [
  "modelCreatorName",
  "creator.name",
  "host.name",
  "creatorName",
  "providerName",
  "model.creator.name",
];
const PALETTE = [
  "#6ea8fe",
  "#38d39f",
  "#ffb454",
  "#ff6b7a",
  "#c792ea",
  "#7fdbff",
  "#f78c6c",
  "#8bd17c",
  "#e5c07b",
  "#56b6c2",
  "#d19a66",
  "#be95ff",
];
const AXIS = "#233252";
const GRID = "#1a253c";
const MUTED = "#8ea0bf";
const FG = "#e8eefb";
const MAX_TABLE_ROWS = 200;

const state: {
  summary: Summary | null;
  group: string;
  dataset: string;
  records: RecordRow[];
  flat: FlatRow[];
  numeric: string[];
  name: string;
  creator: string;
  y: string;
  x: string;
  search: string;
  topN: number;
  logX: boolean;
  showRaw: boolean;
  tab: Tab;
  trendKey: string;
  trendMetric: string;
} = {
  summary: null,
  group: "overview",
  dataset: "",
  records: [],
  flat: [],
  numeric: [],
  name: "",
  creator: "",
  y: "",
  x: "",
  search: "",
  topN: 25,
  logX: false,
  showRaw: false,
  tab: "leaderboard",
  trendKey: "",
  trendMetric: "",
};

const charts = new Map<string, EChartsType>();
let loadToken = 0;
let historyToken = 0;
let runsToken = 0;
let searchTimer: number | undefined;

function el<T extends HTMLElement>(selector: string): T {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`missing element ${selector}`);
  return node;
}

function chartFor(id: string): EChartsType {
  const existing = charts.get(id);
  if (existing) return existing;
  const chart = echarts.init(el<HTMLDivElement>(`#${id}`), undefined, { renderer: "canvas" });
  charts.set(id, chart);
  return chart;
}

function resizeCharts(): void {
  for (const chart of charts.values()) chart.resize();
}

async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

function toast(message: string, isError = false): void {
  const node = el<HTMLDivElement>("#toast");
  node.textContent = message;
  node.className = isError ? "toast error" : "toast";
  node.hidden = false;
  window.setTimeout(() => {
    node.hidden = true;
  }, 4500);
}

function toNumber(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : Number.NaN;
  if (typeof value === "string" && value.trim() !== "") return Number(value);
  return Number.NaN;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  if (typeof value === "boolean") return value ? "✓" : "";
  if (Array.isArray(value)) return JSON.stringify(value);
  return String(value);
}

function formatTime(value: unknown): string {
  if (typeof value !== "string" || !value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function flatten(
  value: Record<string, unknown>,
  prefix = "",
  out: Record<string, unknown> = {},
): Record<string, unknown> {
  for (const [key, item] of Object.entries(value)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (item !== null && typeof item === "object" && !Array.isArray(item)) {
      flatten(item as Record<string, unknown>, name, out);
    } else {
      out[name] = item;
    }
  }
  return out;
}

function scalarColumns(rows: Array<Record<string, unknown>>): string[] {
  const columns = new Set<string>();
  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (key.startsWith("_")) continue;
      if (value === null || typeof value !== "object" || Array.isArray(value)) columns.add(key);
    }
  }
  return [...columns];
}

function numericColumns(rows: Array<Record<string, unknown>>): string[] {
  const columns = new Set<string>();
  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (key.startsWith("_") || key === "id" || key === "slug") continue;
      if (typeof value === "number" && Number.isFinite(value)) columns.add(key);
    }
  }
  return [...columns];
}

function pick(columns: string[], preferred: string[]): string {
  for (const name of preferred) {
    if (columns.includes(name)) return name;
  }
  return columns[0] ?? "";
}

function visibleDatasets(): DatasetMeta[] {
  return (state.summary?.datasets ?? []).filter((item) => item.dashboard || state.showRaw);
}

function renderKpis(): void {
  const summary = state.summary;
  if (!summary) return;
  const run = summary.last_run;
  const totals = run?.totals ?? {};
  const cards: Array<[string, string, string]> = [
    ["Last run", formatTime(run?.finished_at ?? run?.started_at), run?.status ?? "—"],
    ["Active records", summary.active.toLocaleString(), `${visibleDatasets().length} datasets`],
    [
      "New / changed",
      `+${(totals.inserted ?? 0).toLocaleString()} / ~${(totals.updated ?? 0).toLocaleString()}`,
      `${(totals.removed ?? 0).toLocaleString()} removed`,
    ],
    [
      "Last crawl",
      `${totals.pages ?? 0} pages`,
      `${run?.status === "ok" ? "all datasets ok" : "check runs"}`,
    ],
  ];
  const box = el<HTMLElement>("#kpis");
  box.replaceChildren();
  for (const [label, value, hint] of cards) {
    const card = document.createElement("div");
    card.className = "kpi";
    const caption = document.createElement("span");
    caption.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    const small = document.createElement("small");
    small.textContent = hint;
    card.append(caption, strong, small);
    box.append(card);
  }

  const badge = el<HTMLElement>("#run-badge");
  const status = run?.status ?? "unknown";
  badge.className = `badge ${status}`;
  badge.textContent = `${status} · ${formatTime(run?.finished_at)}`;
  el<HTMLElement>("#db-state").textContent = summary.generated_at
    ? `只读 SQLite · 更新于 ${formatTime(summary.generated_at)}`
    : "只读 SQLite";
}

function table(
  container: HTMLElement,
  columns: string[],
  rows: Array<Record<string, unknown>>,
  limit = MAX_TABLE_ROWS,
): void {
  container.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "没有数据";
    container.append(empty);
    return;
  }
  const element = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column;
    headRow.append(cell);
  }
  head.append(headRow);
  const body = document.createElement("tbody");
  for (const row of rows.slice(0, limit)) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const td = document.createElement("td");
      const value = row[column];
      td.textContent = formatValue(value);
      if (typeof value === "number") td.className = "num";
      tr.append(td);
    }
    body.append(tr);
  }
  element.append(head, body);
  container.append(element);
}

function renderOverview(): void {
  const summary = state.summary;
  if (!summary) return;

  const runs = summary.runs;
  const runChart = chartFor("runs-chart");
  runChart.setOption(
    {
      backgroundColor: "transparent",
      grid: { left: 48, right: 20, top: 20, bottom: 36 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#162138",
        borderColor: AXIS,
        textStyle: { color: FG },
      },
      legend: {
        bottom: 0,
        textStyle: { color: MUTED },
        icon: "roundRect",
      },
      xAxis: {
        type: "category",
        data: runs.map((run) => `#${run.id}`),
        axisLine: { lineStyle: { color: AXIS } },
        axisLabel: { color: MUTED },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: MUTED },
        splitLine: { lineStyle: { color: GRID } },
      },
      series: [
        {
          name: "inserted",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: runs.map((run) => run.totals?.inserted ?? 0),
          lineStyle: { width: 2, color: PALETTE[0] },
          itemStyle: { color: PALETTE[0] },
          areaStyle: { opacity: 0.08 },
        },
        {
          name: "updated",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: runs.map((run) => run.totals?.updated ?? 0),
          lineStyle: { width: 2, color: PALETTE[1] },
          itemStyle: { color: PALETTE[1] },
        },
        {
          name: "removed",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: runs.map((run) => run.totals?.removed ?? 0),
          lineStyle: { width: 2, color: PALETTE[3] },
          itemStyle: { color: PALETTE[3] },
        },
      ],
    },
    true,
  );

  const container = el<HTMLElement>("#datasets-table");
  container.replaceChildren();
  const datasets = [...visibleDatasets()].sort((a, b) =>
    `${a.group}/${a.dataset}`.localeCompare(`${b.group}/${b.dataset}`),
  );
  if (!datasets.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "还没有数据，先运行 make once";
    container.append(empty);
    return;
  }
  const element = document.createElement("table");
  const head = document.createElement("thead");
  head.innerHTML =
    "<tr><th>group</th><th>dataset</th><th>label</th><th>records</th><th>last changed</th></tr>";
  const body = document.createElement("tbody");
  for (const dataset of datasets) {
    const tr = document.createElement("tr");
    const group = document.createElement("td");
    group.textContent = dataset.group;
    const name = document.createElement("td");
    const button = document.createElement("button");
    button.className = "link";
    button.textContent = dataset.dataset;
    button.dataset.dataset = dataset.dataset;
    button.dataset.group = dataset.group;
    name.append(button);
    const label = document.createElement("td");
    label.textContent = dataset.label;
    const count = document.createElement("td");
    count.className = "num";
    count.textContent = dataset.count.toLocaleString();
    const changed = document.createElement("td");
    changed.textContent = formatTime(dataset.last_changed);
    tr.append(group, name, label, count, changed);
    body.append(tr);
  }
  element.append(head, body);
  container.append(element);
}

function fillGroupSelect(): void {
  const select = el<HTMLSelectElement>("#group");
  const groups = [...new Set(visibleDatasets().map((item) => item.group))];
  select.replaceChildren();
  const overview = document.createElement("option");
  overview.value = "overview";
  overview.textContent = "overview";
  select.append(overview);
  for (const group of groups) {
    const option = document.createElement("option");
    option.value = group;
    option.textContent = group;
    select.append(option);
  }
  if (!groups.includes(state.group)) state.group = "overview";
  select.value = state.group;
}

function datasetOptions(): DatasetMeta[] {
  return visibleDatasets().filter((item) => item.group === state.group);
}

function fillDatasetSelect(): void {
  const select = el<HTMLSelectElement>("#dataset");
  const items = datasetOptions();
  select.replaceChildren();
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.dataset;
    option.textContent = `${item.dataset} · ${item.label}`;
    select.append(option);
  }
  const selected =
    items.find((item) => item.dataset === state.dataset) ??
    items.find((item) => item.primary) ??
    items[0];
  if (!selected) {
    state.dataset = "";
    select.disabled = true;
    return;
  }
  state.dataset = selected.dataset;
  select.value = selected.dataset;
  select.disabled = false;
}

function fillMetricSelects(): void {
  const ySelect = el<HTMLSelectElement>("#metric-y");
  ySelect.replaceChildren();
  for (const metric of state.numeric) {
    const option = document.createElement("option");
    option.value = metric;
    option.textContent = metric;
    ySelect.append(option);
  }
  state.y = pick(state.numeric, Y_PRIORITY);
  ySelect.value = state.y;
  refreshXOptions();
}

function refreshXOptions(): void {
  const xSelect = el<HTMLSelectElement>("#metric-x");
  const options = state.numeric.filter((metric) => metric !== state.y);
  xSelect.replaceChildren();
  for (const metric of options) {
    const option = document.createElement("option");
    option.value = metric;
    option.textContent = metric;
    xSelect.append(option);
  }
  state.x = pick(options, X_PRIORITY);
  xSelect.value = state.x;
}

function filteredRows(): FlatRow[] {
  const query = state.search.trim().toLowerCase();
  if (!query) return state.flat;
  return state.flat.filter((row) =>
    [state.name, state.creator, "_key"]
      .map((column) => String(row[column] ?? ""))
      .some((value) => value.toLowerCase().includes(query)),
  );
}

function renderBar(rows: FlatRow[]): void {
  const chart = chartFor("bar-chart");
  const points = rows
    .map((row) => ({ row, value: toNumber(row[state.y]) }))
    .filter((point) => Number.isFinite(point.value))
    .sort((a, b) => b.value - a.value)
    .slice(0, state.topN)
    .reverse();
  if (!points.length) {
    chart.clear();
    return;
  }
  chart.setOption(
    {
      backgroundColor: "transparent",
      grid: { left: 170, right: 30, top: 10, bottom: 24 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#162138",
        borderColor: AXIS,
        textStyle: { color: FG },
        formatter: (params: unknown) => {
          const items = params as Array<{ dataIndex: number }>;
          const point = points[items[0]?.dataIndex ?? 0];
          if (!point) return "";
          const name = String(point.row[state.name] ?? point.row._key);
          return `<b>${escapeHtml(name)}</b><br/>${escapeHtml(state.y)}: ${formatValue(
            point.value,
          )}`;
        },
      },
      xAxis: {
        type: "value",
        axisLine: { lineStyle: { color: AXIS } },
        axisLabel: { color: MUTED },
        splitLine: { lineStyle: { color: GRID } },
      },
      yAxis: {
        type: "category",
        data: points.map((point) => String(point.row[state.name] ?? point.row._key)),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: FG, width: 160, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: points.map((point) => point.value),
          barMaxWidth: 18,
          itemStyle: {
            borderRadius: [0, 6, 6, 0],
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: "#3c6fd6" },
              { offset: 1, color: "#6ea8fe" },
            ]),
          },
        },
      ],
    },
    true,
  );
}

function renderScatter(rows: FlatRow[]): void {
  const chart = chartFor("scatter-chart");
  const points = rows
    .map((row) => ({
      row,
      x: toNumber(row[state.x]),
      y: toNumber(row[state.y]),
      creator: state.creator ? String(row[state.creator] ?? "—") : "—",
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
    .filter((point) => !state.logX || point.x > 0);

  if (!points.length) {
    chart.clear();
    return;
  }

  const creatorCounts = new Map<string, number>();
  for (const point of points) {
    creatorCounts.set(point.creator, (creatorCounts.get(point.creator) ?? 0) + 1);
  }
  const topCreators = [...creatorCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([name]) => name);
  const seriesNames = new Set(topCreators);
  const grouped = new Map<string, typeof points>();
  for (const point of points) {
    const key = seriesNames.has(point.creator) ? point.creator : "其他";
    const bucket = grouped.get(key) ?? [];
    bucket.push(point);
    grouped.set(key, bucket);
  }

  chart.setOption(
    {
      backgroundColor: "transparent",
      grid: { left: 54, right: 18, top: 24, bottom: 56 },
      legend: {
        type: "scroll",
        bottom: 0,
        textStyle: { color: MUTED },
        pageTextStyle: { color: MUTED },
      },
      tooltip: {
        trigger: "item",
        backgroundColor: "#162138",
        borderColor: AXIS,
        textStyle: { color: FG },
        formatter: (params: unknown) => {
          const item = params as {
            data?: { value?: [number, number]; name?: string; key?: string; creator?: string };
          };
          const data = item.data;
          if (!data?.value) return "";
          return [
            `<b>${escapeHtml(data.name)}</b>`,
            `${escapeHtml(data.creator)}`,
            `${escapeHtml(state.x)}: ${formatValue(data.value[0])}`,
            `${escapeHtml(state.y)}: ${formatValue(data.value[1])}`,
            `<span style="color:${MUTED}">${escapeHtml(data.key)}</span>`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: state.logX ? "log" : "value",
        name: state.x,
        nameTextStyle: { color: MUTED, fontSize: 10 },
        axisLine: { lineStyle: { color: AXIS } },
        axisLabel: { color: MUTED },
        splitLine: { lineStyle: { color: GRID } },
      },
      yAxis: {
        type: "value",
        name: state.y,
        nameTextStyle: { color: MUTED, fontSize: 10 },
        axisLine: { lineStyle: { color: AXIS } },
        axisLabel: { color: MUTED },
        splitLine: { lineStyle: { color: GRID } },
        scale: true,
      },
      series: [...grouped.entries()].map(([name, group], index) => ({
        name,
        type: "scatter",
        symbolSize: name === "其他" ? 6 : 9,
        itemStyle: { color: PALETTE[index % PALETTE.length], opacity: 0.85 },
        emphasis: { focus: "series" },
        data: group.map((point) => ({
          value: [point.x, point.y],
          name: String(point.row[state.name] ?? point.row._key),
          key: point.row._key,
          creator: point.creator,
        })),
      })),
    },
    true,
  );
}

function tableColumns(): string[] {
  const scalar = scalarColumns(state.flat);
  const preferred = [state.name, "_key", state.creator, state.y, state.x].filter(
    (column) => column && (column === "_key" || scalar.includes(column)),
  );
  const rest = scalar.filter((column) => !preferred.includes(column));
  return [...new Set([...preferred, ...rest])].slice(0, 18);
}

function renderLeaderboard(): void {
  const rows = filteredRows();
  el<HTMLElement>("#row-count").textContent =
    `${rows.length} / ${state.flat.length} 行 · 表格最多显示 ${MAX_TABLE_ROWS} 行`;
  renderBar(rows);
  renderScatter(rows);
  if (!state.numeric.length) {
    table(el<HTMLElement>("#records-table"), scalarColumns(state.flat).slice(0, 12), rows);
    return;
  }
  table(el<HTMLElement>("#records-table"), tableColumns(), rows);
}

function downloadCsv(): void {
  const rows = filteredRows();
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const escape = (value: unknown): string => {
    const text =
      value === null || value === undefined
        ? ""
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);
    return `"${text.replaceAll('"', '""')}"`;
  };
  const lines = [
    columns.map((column) => `"${column.replaceAll('"', '""')}"`).join(","),
    ...rows.map((row) => columns.map((column) => escape(row[column])).join(",")),
  ];
  const blob = new Blob([`\uFEFF${lines.join("\n")}`], {
    type: "text/csv;charset=utf-8",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.dataset || "dataset"}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function loadDataset(dataset: string, force = false): Promise<void> {
  if (!dataset) return;
  const token = ++loadToken;
  try {
    const data = await getJSON<RecordsResponse>(
      `/api/records?dataset=${encodeURIComponent(dataset)}${force ? "&refresh=1" : ""}`,
    );
    if (token !== loadToken) return;
    state.records = data.records;
    state.flat = data.records.map((record) => ({
      ...flatten(record.payload),
      _key: record.key,
      _last_changed: record.last_changed,
    }));
    state.numeric = numericColumns(state.flat);
    const columns = scalarColumns(state.flat);
    state.name = pick(columns, NAME_PRIORITY) || "_key";
    state.creator = pick(columns, CREATOR_PRIORITY) || "";
    state.trendKey = "";
    state.search = "";
    el<HTMLInputElement>("#search").value = "";

    const meta = state.summary?.datasets.find((item) => item.dataset === dataset);
    el<HTMLElement>("#title").textContent = meta?.label ?? dataset;
    el<HTMLElement>("#subtitle").textContent =
      `${dataset} · ${state.flat.length.toLocaleString()} 条记录`;
    fillMetricSelects();
    renderLeaderboard();
    if (state.tab === "trends") await loadTrend();
    if (state.tab === "runs") await loadRuns();
  } catch (error) {
    toast(`读取 ${dataset} 失败: ${error instanceof Error ? error.message : error}`, true);
  }
}

async function loadTrend(): Promise<void> {
  if (!state.flat.length) return;
  const recordSelect = el<HTMLSelectElement>("#trend-record");
  const score = (row: FlatRow): number => {
    const value = toNumber(row[state.y]);
    return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
  };
  const sorted = [...state.flat].sort(
    (a, b) => score(b) - score(a) || String(a[state.name]).localeCompare(String(b[state.name])),
  );
  recordSelect.replaceChildren();
  for (const row of sorted) {
    const option = document.createElement("option");
    option.value = row._key;
    option.textContent = `${String(row[state.name] ?? row._key)} · ${row._key}`;
    recordSelect.append(option);
  }
  if (!state.trendKey || !sorted.some((row) => row._key === state.trendKey)) {
    state.trendKey = sorted[0]?._key ?? "";
  }
  recordSelect.value = state.trendKey;
  await loadHistory();
}

async function loadHistory(): Promise<void> {
  if (!state.dataset || !state.trendKey) return;
  const token = ++historyToken;
  const chart = chartFor("trend-chart");
  try {
    const data = await getJSON<HistoryResponse>(
      `/api/history?dataset=${encodeURIComponent(state.dataset)}&key=${encodeURIComponent(
        state.trendKey,
      )}`,
    );
    if (token !== historyToken) return;
    const rows: Array<Record<string, unknown>> = data.changes.map((change) => ({
      ...flatten(change.payload),
      _observed_at: change.observed_at,
      _change: change.change,
    }));
    el<HTMLElement>("#trend-hint").textContent = `${rows.length} 次变化`;
    const numeric = numericColumns(rows);
    const metricSelect = el<HTMLSelectElement>("#trend-metric");
    metricSelect.replaceChildren();
    for (const metric of numeric) {
      const option = document.createElement("option");
      option.value = metric;
      option.textContent = metric;
      metricSelect.append(option);
    }
    if (!numeric.length) {
      chart.clear();
      table(el<HTMLElement>("#trend-table"), ["_observed_at", "_change"], rows);
      return;
    }
    if (!numeric.includes(state.trendMetric)) {
      state.trendMetric = pick(numeric, Y_PRIORITY);
    }
    metricSelect.value = state.trendMetric;

    const points = rows
      .map((row) => ({
        time: String(row._observed_at),
        value: toNumber(row[state.trendMetric]),
      }))
      .filter((point) => Number.isFinite(point.value));
    chart.setOption(
      {
        backgroundColor: "transparent",
        grid: { left: 58, right: 24, top: 30, bottom: 40 },
        tooltip: {
          trigger: "axis",
          backgroundColor: "#162138",
          borderColor: AXIS,
          textStyle: { color: FG },
        },
        xAxis: {
          type: "time",
          axisLine: { lineStyle: { color: AXIS } },
          axisLabel: { color: MUTED },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          name: state.trendMetric,
          nameTextStyle: { color: MUTED, fontSize: 10 },
          axisLabel: { color: MUTED },
          splitLine: { lineStyle: { color: GRID } },
          scale: true,
        },
        series: [
          {
            type: "line",
            data: points.map((point) => [point.time, point.value]),
            showSymbol: true,
            symbolSize: 6,
            lineStyle: { width: 2, color: PALETTE[0] },
            itemStyle: { color: PALETTE[0] },
            areaStyle: { opacity: 0.08 },
          },
        ],
      },
      true,
    );
    table(
      el<HTMLElement>("#trend-table"),
      ["_observed_at", "_change", ...numeric.slice(0, 8)],
      rows,
    );
  } catch (error) {
    toast(`读取历史失败: ${error instanceof Error ? error.message : error}`, true);
  }
}

async function loadRuns(): Promise<void> {
  if (!state.dataset) return;
  const token = ++runsToken;
  try {
    const data = await getJSON<RunsResponse>(
      `/api/runs?dataset=${encodeURIComponent(state.dataset)}`,
    );
    if (token !== runsToken) return;
    const chart = chartFor("dataset-runs-chart");
    const runs = [...data.runs].reverse();
    chart.setOption(
      {
        backgroundColor: "transparent",
        grid: { left: 44, right: 20, top: 20, bottom: 36 },
        tooltip: {
          trigger: "axis",
          backgroundColor: "#162138",
          borderColor: AXIS,
          textStyle: { color: FG },
        },
        legend: { bottom: 0, textStyle: { color: MUTED }, icon: "roundRect" },
        xAxis: {
          type: "category",
          data: runs.map((run) => `#${run.run_id}`),
          axisLine: { lineStyle: { color: AXIS } },
          axisLabel: { color: MUTED },
        },
        yAxis: {
          type: "value",
          axisLabel: { color: MUTED },
          splitLine: { lineStyle: { color: GRID } },
        },
        series: [
          {
            name: "inserted",
            type: "line",
            smooth: true,
            data: runs.map((run) => run.inserted),
            lineStyle: { color: PALETTE[0] },
            itemStyle: { color: PALETTE[0] },
          },
          {
            name: "updated",
            type: "line",
            smooth: true,
            data: runs.map((run) => run.updated),
            lineStyle: { color: PALETTE[1] },
            itemStyle: { color: PALETTE[1] },
          },
          {
            name: "removed",
            type: "line",
            smooth: true,
            data: runs.map((run) => run.removed),
            lineStyle: { color: PALETTE[3] },
            itemStyle: { color: PALETTE[3] },
          },
        ],
      },
      true,
    );
    table(
      el<HTMLElement>("#dataset-runs-table"),
      [
        "run_id",
        "started_at",
        "status",
        "records",
        "inserted",
        "updated",
        "unchanged",
        "removed",
        "duration_ms",
        "error",
      ],
      data.runs as unknown as Array<Record<string, unknown>>,
    );
  } catch (error) {
    toast(`读取运行记录失败: ${error instanceof Error ? error.message : error}`, true);
  }
}

function setTab(tab: Tab): void {
  state.tab = tab;
  for (const button of document.querySelectorAll<HTMLButtonElement>("#tabs button")) {
    button.classList.toggle("active", button.dataset.tab === tab);
  }
  el<HTMLElement>("#view-leaderboard").hidden = tab !== "leaderboard";
  el<HTMLElement>("#view-trends").hidden = tab !== "trends";
  el<HTMLElement>("#view-runs").hidden = tab !== "runs";
  if (tab === "leaderboard") renderLeaderboard();
  if (tab === "trends") void loadTrend();
  if (tab === "runs") void loadRuns();
  requestAnimationFrame(resizeCharts);
}

function showOverview(): void {
  el<HTMLElement>("#tabs").hidden = true;
  el<HTMLSelectElement>("#dataset").disabled = true;
  el<HTMLElement>("#view-overview").hidden = false;
  el<HTMLElement>("#view-leaderboard").hidden = true;
  el<HTMLElement>("#view-trends").hidden = true;
  el<HTMLElement>("#view-runs").hidden = true;
  el<HTMLElement>("#title").textContent = "Artificial Analysis 数据总览";
  el<HTMLElement>("#subtitle").textContent = "全站榜单增量抓取 · SQLite 只读视图";
  renderOverview();
  requestAnimationFrame(resizeCharts);
}

function showDataset(): void {
  el<HTMLElement>("#tabs").hidden = false;
  el<HTMLElement>("#view-overview").hidden = true;
  setTab(state.tab);
}

async function refresh(force = true): Promise<void> {
  el<HTMLButtonElement>("#refresh").disabled = true;
  try {
    state.summary = await getJSON<Summary>("/api/summary");
    renderKpis();
    fillGroupSelect();
    fillDatasetSelect();
    renderOverview();
    if (state.group === "overview") {
      showOverview();
    } else {
      showDataset();
      await loadDataset(state.dataset, force);
    }
  } catch (error) {
    toast(`刷新失败: ${error instanceof Error ? error.message : error}`, true);
  } finally {
    el<HTMLButtonElement>("#refresh").disabled = false;
  }
}

function bind(): void {
  el<HTMLSelectElement>("#group").addEventListener("change", (event) => {
    state.group = (event.target as HTMLSelectElement).value;
    if (state.group === "overview") {
      showOverview();
      return;
    }
    state.dataset = "";
    fillDatasetSelect();
    showDataset();
    void loadDataset(state.dataset);
  });

  el<HTMLSelectElement>("#dataset").addEventListener("change", (event) => {
    state.dataset = (event.target as HTMLSelectElement).value;
    void loadDataset(state.dataset);
  });

  el<HTMLElement>("#tabs").addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button[data-tab]");
    if (button?.dataset.tab) setTab(button.dataset.tab as Tab);
  });

  el<HTMLInputElement>("#search").addEventListener("input", (event) => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = (event.target as HTMLInputElement).value;
      renderLeaderboard();
    }, 150);
  });

  el<HTMLInputElement>("#topn").addEventListener("input", (event) => {
    state.topN = Number((event.target as HTMLInputElement).value);
    el<HTMLOutputElement>("#topn-value").value = String(state.topN);
    renderLeaderboard();
  });

  el<HTMLInputElement>("#logx").addEventListener("change", (event) => {
    state.logX = (event.target as HTMLInputElement).checked;
    renderScatter(filteredRows());
  });

  el<HTMLSelectElement>("#metric-y").addEventListener("change", (event) => {
    state.y = (event.target as HTMLSelectElement).value;
    refreshXOptions();
    renderLeaderboard();
  });

  el<HTMLSelectElement>("#metric-x").addEventListener("change", (event) => {
    state.x = (event.target as HTMLSelectElement).value;
    renderScatter(filteredRows());
  });

  el<HTMLButtonElement>("#download").addEventListener("click", downloadCsv);
  el<HTMLButtonElement>("#refresh").addEventListener("click", () => void refresh(true));

  el<HTMLSelectElement>("#trend-record").addEventListener("change", (event) => {
    state.trendKey = (event.target as HTMLSelectElement).value;
    void loadHistory();
  });

  el<HTMLSelectElement>("#trend-metric").addEventListener("change", (event) => {
    state.trendMetric = (event.target as HTMLSelectElement).value;
    void loadHistory();
  });

  el<HTMLInputElement>("#raw").addEventListener("change", (event) => {
    state.showRaw = (event.target as HTMLInputElement).checked;
    fillGroupSelect();
    if (state.group === "overview") {
      showOverview();
      return;
    }
    fillDatasetSelect();
    showDataset();
    void loadDataset(state.dataset);
  });

  el<HTMLElement>("#datasets-table").addEventListener("click", (event) => {
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>("button[data-dataset]");
    if (!target?.dataset.dataset) return;
    state.group = target.dataset.group ?? "other";
    state.dataset = target.dataset.dataset;
    el<HTMLSelectElement>("#group").value = state.group;
    fillDatasetSelect();
    showDataset();
    void loadDataset(state.dataset);
  });

  window.addEventListener("resize", resizeCharts);
}

bind();
void refresh(true);
