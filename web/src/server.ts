import { Database } from "bun:sqlite";
import { resolve } from "node:path";
import index from "./index.html";

interface DatasetMeta {
  dataset: string;
  group: string;
  label: string;
  primary?: boolean;
  dashboard?: boolean;
  count?: number;
  last_changed?: string | null;
}

interface Manifest {
  generated_at?: string;
  last_run?: unknown;
  datasets: DatasetMeta[];
}

interface CountRow {
  dataset: string;
  active: number;
  last_changed: string | null;
}

interface RecordRow {
  record_key: string;
  payload: string;
  first_seen: string;
  last_seen: string;
  last_changed: string;
}

interface HistoryRow {
  observed_at: string;
  change: string;
  payload: string;
}

const root = resolve(import.meta.dir, "../..");
const dbPath = process.env.AA_DB ?? resolve(root, "data", "aa.db");
const manifestPath = process.env.AA_MANIFEST ?? resolve(root, "data", "datasets.json");
const port = Number(process.env.AA_PORT ?? process.env.PORT ?? 8501);
const hostname = process.env.AA_HOST ?? "127.0.0.1";

let db: Database;
try {
  db = new Database(dbPath, { readonly: true });
} catch (error) {
  console.error(`cannot open ${dbPath}: ${error instanceof Error ? error.message : error}`);
  process.exit(1);
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function loadManifest(): Promise<Manifest | null> {
  try {
    return (await Bun.file(manifestPath).json()) as Manifest;
  } catch {
    return null;
  }
}

function fallbackDatasets(): DatasetMeta[] {
  const rows = db.query("SELECT DISTINCT dataset FROM latest ORDER BY dataset").all() as Array<{
    dataset: string;
  }>;
  return rows.map((row) => ({
    dataset: row.dataset,
    group: "other",
    label: row.dataset,
    dashboard: true,
    primary: false,
  }));
}

function datasetCatalog(manifest: Manifest | null): DatasetMeta[] {
  const base = manifest?.datasets?.length ? manifest.datasets : fallbackDatasets();
  const counts = new Map<string, CountRow>();
  for (const row of db
    .query(
      "SELECT dataset, COUNT(*) AS active, MAX(last_changed) AS last_changed FROM latest GROUP BY dataset",
    )
    .all() as CountRow[]) {
    counts.set(row.dataset, row);
  }
  return base.map((item) => {
    const count = counts.get(item.dataset);
    return {
      ...item,
      dashboard: item.dashboard !== false,
      primary: item.primary === true,
      count: count?.active ?? 0,
      last_changed: count?.last_changed ?? null,
    };
  });
}

function parseTotals(value: unknown): unknown {
  if (typeof value !== "string" || !value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

async function summary(): Promise<Response> {
  const manifest = await loadManifest();
  const datasets = datasetCatalog(manifest);
  const rawRuns = db
    .query(
      "SELECT id, started_at, finished_at, status, totals FROM runs ORDER BY id DESC LIMIT 120",
    )
    .all() as Array<{
    id: number;
    started_at: string;
    finished_at: string | null;
    status: string;
    totals: string | null;
  }>;
  const runs = rawRuns.map((run) => ({ ...run, totals: parseTotals(run.totals) })).reverse();
  const active = datasets.reduce((sum, item) => sum + (item.count ?? 0), 0);
  return json({
    generated_at: manifest?.generated_at ?? null,
    last_run: runs.length ? runs[runs.length - 1] : null,
    runs,
    datasets,
    active,
  });
}

const recordsStmt = db.query(
  "SELECT record_key, payload, first_seen, last_seen, last_changed FROM latest WHERE dataset = ? ORDER BY record_key",
);
const historyStmt = db.query(
  "SELECT observed_at, change, payload FROM changes WHERE dataset = ? AND record_key = ? ORDER BY id",
);
const datasetRunsStmt = db.query(
  "SELECT d.run_id, r.started_at, r.status, d.records, d.inserted, d.updated, d.unchanged, d.removed, d.duration_ms, d.error FROM dataset_runs AS d JOIN runs AS r ON r.id = d.run_id WHERE d.dataset = ? ORDER BY d.run_id DESC LIMIT 120",
);

const recordCache = new Map<string, { at: number; value: unknown }>();
const CACHE_MS = 15_000;

function records(dataset: string, refresh: boolean): Response {
  const hit = recordCache.get(dataset);
  if (!refresh && hit && Date.now() - hit.at < CACHE_MS) return json(hit.value);
  const rows = recordsStmt.all(dataset) as RecordRow[];
  const value = {
    dataset,
    records: rows.map((row) => ({
      key: row.record_key,
      payload: JSON.parse(row.payload),
      first_seen: row.first_seen,
      last_seen: row.last_seen,
      last_changed: row.last_changed,
    })),
  };
  recordCache.set(dataset, { at: Date.now(), value });
  return json(value);
}

function history(dataset: string, key: string): Response {
  const rows = historyStmt.all(dataset, key) as HistoryRow[];
  return json({
    dataset,
    key,
    changes: rows.map((row) => ({
      observed_at: row.observed_at,
      change: row.change,
      payload: JSON.parse(row.payload),
    })),
  });
}

function runs(dataset: string): Response {
  const rows = datasetRunsStmt.all(dataset) as Array<{
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
  }>;
  return json({ dataset, runs: rows });
}

const server = Bun.serve({
  port,
  hostname,
  routes: {
    "/": index,
    "/api/summary": () => summary(),
    "/api/records": (request: Request) => {
      const url = new URL(request.url);
      const dataset = url.searchParams.get("dataset");
      if (!dataset) return json({ error: "dataset is required" }, 400);
      return records(dataset, url.searchParams.has("refresh"));
    },
    "/api/history": (request: Request) => {
      const url = new URL(request.url);
      const dataset = url.searchParams.get("dataset");
      const key = url.searchParams.get("key");
      if (!dataset || !key) return json({ error: "dataset and key are required" }, 400);
      return history(dataset, key);
    },
    "/api/runs": (request: Request) => {
      const dataset = new URL(request.url).searchParams.get("dataset");
      if (!dataset) return json({ error: "dataset is required" }, 400);
      return runs(dataset);
    },
    "/api/health": () => json({ ok: true }),
  },
  error(error: unknown) {
    console.error(error);
    return json({ error: error instanceof Error ? error.message : String(error) }, 500);
  },
});

console.log(`dashboard http://${server.hostname}:${server.port}`);
console.log(`db       ${dbPath}`);
