// Local PostgreSQL playground (PGlite = real Postgres in WASM). Run: node server.mjs -> http://localhost:8000
// Each datasets/*.sql file gets its own in-memory database. Reset recreates it from the file.
import { PGlite } from "@electric-sql/pglite";
import { createServer } from "node:http";
import { readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";
import { spawn } from "node:child_process";

const ROOT = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8000);
const MAX_ROWS = 1000;
const DBS = new Map();
const keep = (v) => v; // dates/timestamps come back as the exact text Postgres prints
const parsers = { 1082: keep, 1114: keep, 1184: keep, 1083: keep, 1186: keep, 114: keep, 3802: keep }; // json/jsonb shown as text
const NUMERIC_OIDS = new Set([20, 21, 23, 700, 701, 1700]);

const names = () => readdirSync(join(ROOT, "datasets")).filter((f) => f.endsWith(".sql")).map((f) => f.slice(0, -4)).sort();

async function load(name) {
  const db = new PGlite();
  await db.exec(readFileSync(join(ROOT, "datasets", name + ".sql"), "utf8"));
  DBS.set(name, db);
}

// Dataset display names live in datasets/labels.json ({file-name: label}); renaming never touches the .sql file.
const LABELS = join(ROOT, "datasets", "labels.json");
const labels = () => (existsSync(LABELS) ? JSON.parse(readFileSync(LABELS, "utf8")) : {});

async function schema(name) {
  const db = DBS.get(name);
  const cols = (await db.query(`
    SELECT c.table_name t, c.column_name n, c.data_type ty, c.is_nullable = 'YES' nullable,
      EXISTS (SELECT 1 FROM information_schema.key_column_usage k JOIN information_schema.table_constraints tc USING (constraint_name, table_schema)
              WHERE tc.constraint_type='PRIMARY KEY' AND k.table_name=c.table_name AND k.column_name=c.column_name AND k.table_schema='public') pk
    FROM information_schema.columns c WHERE c.table_schema='public' ORDER BY c.table_name, c.ordinal_position`)).rows;
  const tables = [];
  for (const t of [...new Set(cols.map((c) => c.t))]) {
    const n = (await db.query(`SELECT count(*)::int n FROM "${t}"`)).rows[0].n;
    tables.push({ table: t, rows: n, columns: cols.filter((c) => c.t === t).map((c) => ({ name: c.n, type: c.ty, pk: c.pk, nullable: c.nullable })) });
  }
  // Relationships: declared foreign keys; if the dataset declares none, infer them from "column name == another table's primary key name".
  const col = (t, n) => tables.find((x) => x.table === t).columns.find((c) => c.name === n);
  const fks = (await db.query(`
    SELECT c.conrelid::regclass::text t, a.attname col, c.confrelid::regclass::text rt, af.attname rcol
    FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
    WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1 AND c.connamespace = 'public'::regnamespace`)).rows;
  let relations = fks.map((f) => ({ from: { table: f.t, column: f.col }, to: { table: f.rt, column: f.rcol }, inferred: false }));
  if (!relations.length) {
    const pk = Object.fromEntries(tables.map((t) => [t.table, t.columns.filter((c) => c.pk).map((c) => c.name)]));
    for (const t of tables) for (const c of t.columns) for (const u of tables)
      if (u.table !== t.table && pk[u.table].length === 1 && pk[u.table][0] === c.name && !(pk[t.table].length === 1 && pk[t.table][0] === c.name))
        relations.push({ from: { table: t.table, column: c.name }, to: { table: u.table, column: c.name }, inferred: true });
  }
  for (const r of relations) { const c = col(r.from.table, r.from.column); r.unique = c.pk; r.nullable = c.nullable; }
  return { label: labels()[name] || name, tables, relations };
}

// Snowflake mode: translate to Postgres with sqlglot, run on the same engine, upper-case column names like Snowflake does.
const translate = (sql) => new Promise((ok) => {
  const p = spawn(join(ROOT, ".venv/bin/python"), [join(ROOT, "translate.py")]);
  let out = ""; p.stdout.on("data", (c) => (out += c));
  p.on("error", () => ok({ error: "Snowflake translator missing: run  python3 -m venv .venv && .venv/bin/pip install sqlglot" }));
  p.on("close", () => { try { ok(JSON.parse(out)); } catch { ok({ error: "translator failed" }); } });
  p.stdin.end(sql);
});

async function run(name, sql, dialect = "postgres") {
  if (!DBS.has(name)) await load(name);
  const db = DBS.get(name), t = performance.now();
  try {
    let translated = null;
    if (dialect === "snowflake") {
      const tr = await translate(sql);
      if (tr.error) return { error: "Snowflake syntax error: " + tr.error };
      translated = tr.sql; sql = translated;
    }
    const results = await db.exec(sql, { rowMode: "array", parsers });
    const r = results.filter((x) => x.fields?.length).pop() ?? results.at(-1) ?? { rows: [], fields: [] };
    const cols = r.fields.map((f) => (dialect === "snowflake" ? f.name.toUpperCase() : f.name));
    return { translated, columns: cols, numeric: r.fields.map((f) => NUMERIC_OIDS.has(f.dataTypeID)), rows: r.rows.slice(0, MAX_ROWS),
      truncated: r.rows.length > MAX_ROWS, ms: Math.round((performance.now() - t) * 10) / 10,
      command: cols.length ? null : `${r.command ?? "OK"}${r.affectedRows ? " " + r.affectedRows : ""}` };
  } catch (e) {
    return { error: e.message + (e.position ? `\n(at character ${e.position})` : "") };
  }
}

const send = (res, code, body, type = "application/json") => {
  res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body, (k, v) => (typeof v === "bigint" ? v.toString() : v)));
};
const readBody = (req) => new Promise((ok) => { let s = ""; req.on("data", (c) => (s += c)); req.on("end", () => ok(JSON.parse(s || "{}"))); });

createServer(async (req, res) => {
  try {
    if (req.method === "GET" && (req.url === "/" || req.url === "/index.html")) return send(res, 200, readFileSync(join(ROOT, "static", "index.html")), "text/html; charset=utf-8");
    if (req.method === "GET" && req.url === "/api/datasets") {
      for (const n of names()) if (!DBS.has(n)) await load(n);
      const out = {};
      for (const n of names()) out[n] = await schema(n);
      return send(res, 200, out);
    }
    if (req.method === "POST") {
      const b = await readBody(req);
      if (req.url === "/api/query") return send(res, 200, await run(b.dataset, b.sql, b.dialect));
      if (req.url === "/api/rename") {
        const label = String(b.label || "").trim().slice(0, 60);
        if (!names().includes(b.dataset) || !label) return send(res, 400, { error: "invalid dataset or empty name" });
        writeFileSync(LABELS, JSON.stringify({ ...labels(), [b.dataset]: label }, null, 2));
        return send(res, 200, { ok: true, label });
      }
      if (req.url === "/api/reset") { await load(b.dataset); return send(res, 200, { ok: true }); }
    }
    send(res, 404, { error: "not found" });
  } catch (e) { send(res, 500, { error: String(e.message || e) }); }
}).listen(PORT, "127.0.0.1", () => console.log(`PostgreSQL playground on http://localhost:${PORT}`));
