# Migration Validation & Mapping Tool

A configuration-driven web application for validating CSV-based database
migrations: upload source and target CSV exports, map columns visually,
define matching keys and validation rules, run reconciliation against
millions of rows, investigate every difference, and export a client-ready
report — without writing a line of Python.

This is **Phase 1 (MVP)** of the three-phase plan below, built and verified
end‑to‑end (backend tests, API integration tests, and a manual full-stack
run through the real UI). Phase 1 already includes some Phase 2/3 pieces
(field-level comparison, date/numeric normalization, mapping templates,
background jobs, run history/comparison) because the underlying engine and
schema needed to support them from day one to stay genuinely
configuration-driven — see [What's implemented](#3-whats-implemented-vs-roadmap).

---

## 1. Quick start

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -r requirements.txt
cp ../.env.example ../.env      # edit if needed
uvicorn main:app --reload --port 8000
```

The API is now live at `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. In dev, Vite proxies `/api/*` to the backend
on port 8000 (see `frontend/vite.config.ts`) — no extra configuration
needed.

### Sample data

```bash
python3 sample_data/generate_sample_data.py
```

This regenerates `sample_data/customer_master.csv` / `customer.csv` (the
exact example from the spec — 1003 missing in target, 1004 extra) and can
also generate a 1.2M-row `large_source.csv` / `large_target.csv` pair for
performance testing (kept out of the repo by default because of size —
regenerate locally when you want to benchmark).

### Tests

```bash
cd backend  # or project root with backend on PYTHONPATH — see tests/conftest.py
pip install -r requirements.txt
pytest ../tests -v
```

10 engine tests (exact match, duplicates, case/whitespace, nulls, numeric
& date normalization, composite keys, field comparison, blank keys) and 3
API integration tests all pass against this codebase.

---

## 2. Architecture

```
Frontend (React + TypeScript + Tailwind)
        |  REST/JSON
        v
FastAPI (backend/main.py)
        |
        +-- api/            -- thin HTTP routing + request validation only
        +-- services/        -- file inspection, mapping suggestions, background job runner
        +-- validators/       -- the matching/validation engine (all business logic)
        +-- exporters/        -- Excel/CSV report generation
        +-- utils/            -- safe storage paths, user-facing error helpers
        |
        v
DuckDB (in-process, queries Parquet files directly -- no data ever
        fully loaded into a Python list/DataFrame for large datasets)
        |
        v
Parquet files on disk, isolated per project           SQLite (backend/storage/app.db)
(uploads/, parquet/, results/, exports/)               -- projects, files, mappings, run
                                                          summaries/metadata only
```

**Why this split:** SQLite is good at small, relational, frequently-updated
configuration data (projects, mapping definitions, run status) but is the
wrong tool for scanning/joining millions of rows. DuckDB is the opposite —
excellent at exactly that, directly against columnar Parquet files, without
a separate database server to run. Row-level migration data therefore never
touches SQLite; only summaries and small result tables (missing/extra/
duplicates/field-diffs) do, and even those are queried live from Parquet
rather than being pulled into Python.

### How large CSVs are handled
1. On upload, the file is streamed to disk in 1MB chunks (`api/files.py`)
   — never buffered fully in memory.
2. `services/file_inspector.py` uses DuckDB's `read_csv_auto` to detect
   encoding (via `chardet`, sampled), delimiter (via `csv.Sniffer`,
   sampled), and column types — all via streaming reads, not full loads.
3. The CSV is written **once** to a compressed columnar Parquet file next
   to it. Every subsequent operation (preview, mapping suggestions,
   validation, export) reads that Parquet file instead of re-parsing the
   CSV, which is dramatically faster for repeated access.
4. `validators/engine.py` runs the entire matching/comparison pipeline as
   SQL inside DuckDB (joins, `GROUP BY`, `COUNT(DISTINCT ...)`, etc.).
   DuckDB streams and spills to disk as needed — the Python process never
   materializes the full source or target dataset.
5. Benchmarked locally at **~1.5M source rows x ~1.46M target rows,
   3 compared fields, full validation (existence + duplicates + field-level
   comparison) in ~90 seconds** on a modest container. This scales
   further by adding DuckDB worker threads (`PRAGMA threads=N`) or moving
   to a machine with more cores — no code changes required.

### How matching works
- Each mapped field can be marked as (part of) the **matching key**.
  Multiple key fields are concatenated into one composite key
  (`CONCAT_WS`) after each is independently normalized — this is how
  `FirstName + LastName + DOB` becomes one logical key.
- Every raw value passes through a configurable **normalization
  pipeline** before comparison: trim -> null-token detection -> (numeric:
  canonical numeric string, e.g. `001234`/`1234`/`1234.0` -> `1234`) or
  (date: tries a list of common formats via `TRY_STRPTIME` and casts to
  ISO) -> optional case-folding.
- Source and target are joined on the normalized key. `COUNT(DISTINCT
  key)` gives unique customer counts; `NOT IN` anti-joins give missing/
  extra; an inner join on distinct keys gives matched.

### How duplicates are detected
`GROUP BY normalized_key HAVING COUNT(*) > 1`, run independently against
source and target. Duplicate keys are **excluded from field-level
comparison** (the match would be ambiguous — which of the 2 source rows
should be compared to which target row?) and instead surfaced in their
own "Duplicates" report/tab so the client can resolve them explicitly.

### How missing/extra records are calculated
- **Missing** = source rows whose normalized key doesn't exist anywhere
  in the target's distinct key set.
- **Extra** = target rows whose normalized key doesn't exist anywhere in
  the source's distinct key set.
- Both exclude rows with a blank/null key component — those are counted
  and reported separately (`source_rows_with_null_key` /
  `target_rows_with_null_key`) rather than silently treated as "missing".

### How field-level comparison works
For every mapped field flagged "compare in validation" (i.e. not itself
part of the matching key), the engine builds one `SELECT` per field over
the **unambiguous 1:1 matches only** (keys with count = 1 on both sides),
unions them into one long/tidy table (`matching_key, field_name,
source_value, target_value, status`), and only persists rows where
`status != 'MATCH'`. Status is one of `MATCH`, `CHANGED`,
`NULL_IN_SOURCE`, `NULL_IN_TARGET`, `TYPE_MISMATCH_SOURCE`,
`TYPE_MISMATCH_TARGET`. This keeps the stored diff table proportional to
the number of actual differences, not the number of matched rows — the
UI's "Changed" tab aggregates it back to one row per differing key.
Opening a single record (Difference Explorer -> click a row) re-runs a
**cheap, single-key** comparison across *all* compared fields (including
ones that matched) on demand, so the persisted table never needs to store
full-width rows for every match.

### How multi-table relationships work (architecture in place, Phase 3 UI pending)
`MappingConfig` rows are not limited to one per project — a project can
hold many (`source_file -> target_file`) mapping configs, each optionally
pointing at a `parent_mapping_id`. This is exactly the shape needed for
`customer_master -> customer`, `address -> customer_address`,
`contact -> customer_contact`, etc., all within one project, plus a way to
express "this mapping's target key must exist in the parent mapping's
target key" for referential-integrity checks (Section 13 of the spec).
The engine's key-building and anti-join logic already generalizes to that
directly; Phase 3 adds the UI to define the relationship graph and an
orphan-record report built on the same anti-join pattern used for
missing/extra.

### Where results are stored
Every validation run gets its own folder
(`storage/results/<project_id>/<run_id>/`) containing `missing.parquet`,
`extra.parquet`, `changed_keys.parquet`, `field_diffs.parquet`,
`duplicates_source.parquet`, `duplicates_target.parquet`. The run's
**summary** (counts only) is stored in SQLite for fast dashboard loads;
the Difference Explorer tabs query the Parquet files directly with
server-side pagination/search/sort (`api/results.py`), so opening the
results page never re-runs the full validation and never sends more than
one page of rows to the browser.

### How performance is maintained
- Streamed uploads, streamed CSV inspection, one-time Parquet conversion.
- All heavy computation is SQL pushed into DuckDB, not Python loops.
- Validation runs execute in a background thread pool
  (`services/job_runner.py`) so the HTTP request returns immediately; the
  frontend polls run status/progress every 800ms.
- Results are paginated server-side (`LIMIT`/`OFFSET` in DuckDB) — the
  browser never receives more than one page (default 25–50 rows) of the
  difference tables, regardless of how many millions of rows were
  processed.
- Excel export streams sheets from Parquet via `openpyxl`; very large
  result sets are capped per sheet (200k rows) with a note to use the CSV
  export for the complete dataset, rather than trying to build a
  multi-hundred-MB workbook in memory.

### How the client uses the application
1. **Create a project** for the migration (e.g. "Customer Database
   Migration - September 2026").
2. **Upload** the old-system and new-system CSV exports (drag-and-drop,
   multiple files). The tool inspects each file immediately — row/column
   counts, encoding, delimiter, a preview — and flags any file it
   couldn't parse with a plain-English reason.
3. **Assign roles** (Source / Target) to each file.
4. **Configure mapping**: pick a source and target file, click "Suggest
   Mappings" for a pre-filled starting point (never auto-applied — the
   client reviews and edits every row), mark which field(s) form the
   matching key, set data types and normalization rules, save.
5. **Run validation**. Progress is shown live; when it completes, a
   dashboard shows source/target/matched/missing/extra/changed/duplicate
   counts.
6. **Investigate** any tab (Missing / Extra / Changed / Field Differences
   / Duplicates) with search, sort, and pagination; click any row to see
   the full source and target record side by side.
7. **Export** a single Excel workbook (Summary + every tab as its own
   sheet) or a CSV of just the tab they're looking at.
8. **Re-run** later (e.g. after the client fixes the missing records) and
   compare the two runs' summaries side by side in the History tab.

---

## 3. What's implemented vs. roadmap

### Phase 1 (this build) - done
- Project creation & management
- Multi-CSV drag-and-drop upload with streamed inspection (encoding,
  delimiter, row/column counts, preview, parse warnings)
- Source/Target classification, editable per file
- Visual column mapping (many-source -> one-target supported), with
  required/matching-key/compare toggles per field
- Auto-mapping suggestions (exact name, known synonyms, substring, fuzzy
  match) — always reviewable/editable, never auto-applied
- Trim, case-insensitive, numeric, and date normalization
- Composite (multi-column) matching keys
- Record existence validation (matched/missing/extra), unique customer
  counts
- Duplicate key detection (source & target independently)
- Field-level comparison with per-field status (`MATCH`/`CHANGED`/
  `NULL_IN_SOURCE`/`NULL_IN_TARGET`/type mismatches)
- Background validation jobs with live progress polling
- Dashboard with summary stat cards
- Difference Explorer: 6 tabs, server-side search/sort/pagination,
  click-through to full record detail
- CSV export per tab; one combined Excel report (summary + all tabs)
- Mapping templates (save/list/duplicate/delete) — reusable across
  projects
- Run history with side-by-side run comparison
- User-friendly error messages throughout (no stack traces / raw SQL
  ever reaches the client)
- Per-project file isolation, sanitized filenames, no arbitrary code
  execution, no data sent to external AI APIs
- Automated tests: 10 engine tests + 3 API integration tests, all passing

### Phase 2 (partially pulled into Phase 1; remaining items)
- Field-level comparison, date & numeric normalization, mapping
  templates, background jobs, and progress tracking are already done
  above because the engine needed this shape from the start
- Remaining: safe, sandboxed custom transformation expressions beyond
  upper/lower/trim (e.g. `FirstName + LastName` concatenation into a
  *non-key* target field — composite matching keys already support the
  key case); a richer auto-mapping model using sample-value profiling in
  addition to column names

### Phase 3 (not yet built — architecture is ready for it)
- UI for defining multi-table relationships between several
  `MappingConfig`s in one project (schema already supports
  `parent_mapping_id`)
- Referential-integrity / orphan-record report (same anti-join pattern as
  missing/extra, applied to a child mapping's target key against its
  parent mapping's target key)
- Authentication (the API is structured so an auth dependency can be
  added to every router without restructuring)
- Configurable file-retention/cleanup policy and a scheduled cleanup job
- Data-type validation as its own first-class rule (today it's folded
  into field-level comparison's `TYPE_MISMATCH_*` statuses for numeric
  fields; extending to a dedicated report is straightforward)

---

## 4. Project structure

```
app/
├── backend/
│   ├── main.py                  FastAPI app, CORS, global error handler
│   ├── database.py              SQLite engine/session setup
│   ├── api/                     HTTP routes only (thin)
│   │   ├── projects.py
│   │   ├── files.py
│   │   ├── mappings.py          + mapping templates
│   │   ├── validation.py        run start/status/compare
│   │   ├── results.py           paginated difference-explorer queries
│   │   ├── export.py
│   │   └── schemas.py           Pydantic request/response models
│   ├── models/
│   │   └── models.py            SQLModel tables
│   ├── services/
│   │   ├── file_inspector.py    encoding/delimiter/schema detection, CSV→Parquet
│   │   ├── mapping_suggester.py auto-mapping suggestions
│   │   └── job_runner.py        background validation execution
│   ├── validators/
│   │   └── engine.py            the core DuckDB matching/validation engine
│   ├── exporters/
│   │   └── excel_exporter.py    Excel + CSV report generation
│   ├── utils/
│   │   ├── storage_paths.py     safe, per-project file isolation
│   │   └── errors.py            user-friendly error helpers
│   └── requirements.txt
│
├── frontend/                    React + TypeScript + Tailwind (Vite)
│   └── src/
│       ├── api/client.ts        typed API client
│       ├── types.ts
│       ├── components/          Layout, DataTable (server-paginated), ui.tsx
│       └── pages/
│           ├── ProjectsPage.tsx
│           ├── ProjectDetailPage.tsx   step navigation
│           └── project/
│               ├── FilesTab.tsx
│               ├── MappingTab.tsx
│               ├── ValidationTab.tsx   run + dashboard + difference explorer
│               └── HistoryTab.tsx
│
├── storage/                      created at runtime — uploads/parquet/results/exports
├── sample_data/                  generator script + the spec's example CSVs
├── tests/                        pytest: engine + API integration tests
├── .env.example
└── README.md                     you are here
```

---

## 5. Production deployment notes

- **Backend**: run behind a process manager (`uvicorn main:app --workers
  N` behind nginx/Caddy, or a container). The background job executor
  currently uses an in-process `ThreadPoolExecutor` for simplicity — for
  multi-process/horizontally-scaled deployments, swap
  `services/job_runner.py` for Celery/RQ backed by Redis; the API
  contract (`POST /runs` → poll `GET /runs/{id}`) doesn't need to change.
- **Frontend**: `npm run build` produces a static `dist/` bundle — serve
  it from any static host/CDN, or the same nginx in front of the API.
  Set `VITE_API_BASE_URL` if the API isn't reachable at a relative `/api`
  path in production.
- **Database**: SQLite is fine for a single-instance MVP deployment. For
  multi-instance deployments, point `APP_DB_PATH`/`database.py` at
  Postgres instead (SQLModel makes this a connection-string change).
- **Storage**: mount `APP_STORAGE_ROOT` on persistent/shared storage (EBS,
  NFS, or object storage via a small adapter) if running more than one
  backend instance.
- **Security**: add an auth dependency (API key, JWT, or SSO) to the
  routers in `api/` before exposing this outside a trusted network — the
  MVP intentionally ships without auth per the phased plan, but the file
  isolation, filename sanitization, and "no data leaves the environment"
  properties are already in place.
- **Retention**: nothing currently auto-deletes old uploads/results.
  Add a scheduled job that walks `storage/` and removes project data past
  a configurable retention window.
