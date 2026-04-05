# PubMiner

PubMiner is a literature mining workspace for PubMed and PMC.

It combines:

- a `Next.js` frontend for search, article review, task monitoring, and result preview
- a `FastAPI` backend for PubMed retrieval, PMC full-text download, LLM extraction, and CSV export

The current workflow is:

1. Search PubMed or paste PMIDs
2. Load the first page of article metadata while the full PMID set is saved as a backend search session
3. Review article metadata, charts, and automatic current-page OA PDF checks
4. Select loaded articles or target the full matched search session
5. Run chunked extraction tasks with persistent task tracking
6. Preview and download CSV outputs for completed or partial runs

## Architecture

### Frontend

- Framework: `Next.js 16`, `React 19`, `TypeScript`
- Styling: `Tailwind CSS`, `shadcn/ui`
- State: `Zustand`
- Charts: `ECharts`

Main frontend areas:

- `src/components/pubminer/search-section.tsx`
  Search input and query builder
- `src/components/pubminer/search-results-section.tsx`
  Search result list, filters, charts, pagination, article selection
- `src/components/pubminer/extraction-setup-section.tsx`
  LLM extraction options and custom fields
- `src/components/pubminer/tasks-section.tsx`
  Task queue and task detail diagnostics
- `src/components/pubminer/results-section.tsx`
  Result preview, column controls, article mapping, and CSV download

### Backend

- Framework: `FastAPI`
- Data source: `NCBI Entrez` for PubMed and citation links
- Full text: `PMC BioC API`
- LLM extraction: `Zhipu GLM`
- Export: `pandas` CSV export

Main backend areas:

- `PubMiner/api_server.py`
  API entry point and task orchestration
- `PubMiner/pubminer/fetcher/`
  PubMed search and metadata parsing
- `PubMiner/pubminer/downloader/`
  PMC full-text download, OA PDF resolution, parsing, fallback logic, and cache
- `PubMiner/pubminer/extractor/`
  LLM extraction client and schema generation
- `PubMiner/pubminer/exporter/`
  CSV column mapping, ordering, and export logic

## Implemented Features

### Search and Review

- PubMed query builder
- direct PMID list import
- session-backed incremental loading for search results
- first-page metadata loading for large queries
- current-page automatic OA PDF checking
- manual current-page OA refresh and batch OA PDF download
- metadata review before extraction
- article filtering and selection
- PubMed-style result statistics, including year distribution

### Extraction Workflow

- search and extraction are separated into distinct steps
- extraction can target either selected loaded articles or the full matched backend search session
- built-in extraction schema for common literature fields
- custom extraction field support
- optional citation fetching
- PMC full-text retrieval with structured section parsing
- fallback full-text assembly when section parsing is weak
- article-level extraction status tracking
- extraction cache keyed by PMID, schema, model, and text hash
- chunk-based processing for large runs

### Task Diagnostics

- persistent SQLite-backed task queue and task detail panel
- full-text download report
- fallback usage report
- cache hit reporting
- citation status reporting
- article mapping from search result to final output row
- chunk progress reporting and retry actions for failed chunks or failed articles

### Result Handling

- preview extracted CSV data in the UI
- switch between `Metadata`, `LLM`, and `Full` preview modes
- grouped visible-column controls
- result preview and CSV download for both `completed` and `partial` tasks
- multiple CSV download modes:
  - metadata only
  - LLM fields only
  - full table

## Retrieval Pipeline

The backend uses the following retrieval flow:

1. `Entrez.esearch`
   Find PMIDs from a PubMed query and persist them as a backend search session
2. paged `Entrez.efetch`
   Fetch PubMed XML metadata only for the currently loaded slice
3. optional `Entrez.elink`
   Fetch citation and reference links when enabled
4. `PMC BioC API`
   Download full text for records with a PMCID
5. OA PDF resolver
   Resolve legal OA PDF candidates with PMC-first logic plus optional DOI fallbacks
6. section parser + fallback
   Build usable extraction text from PMC content
7. `ZhipuExtractor`
   Extract structured fields with a schema-driven prompt
8. `CSVExporter`
   Merge metadata and LLM results into ordered CSV output

## Recent Engineering Improvements

This project has already been improved beyond the initial scaffold. Notable changes include:

- search preview and LLM extraction split into separate UX stages
- search sessions added so large query sets no longer require full metadata hydration before first render
- dynamic custom extraction fields wired end-to-end
- result preview in the frontend
- article-level mapping between search results and extraction outputs
- PMC full-text caching in `download/pmc_cache`
- citation fetching enabled only when requested
- citation fetching parallelized with the main extraction flow
- enhanced section parsing with fallback logic
- PubMed metadata retry and split-batch fallback for incomplete reads
- OA PDF resolution narrowed to current-page automatic checks for large result sets
- extraction scope can now use the full matched backend search session
- task and search-session state persisted locally in SQLite
- CSV export modes and stable output naming
- richer bibliographic metadata surfaced before extraction

## Directory Layout

```text
.
├─ src/                         Frontend application
│  ├─ app/
│  ├─ components/
│  │  ├─ pubminer/
│  │  └─ ui/
│  └─ lib/
├─ PubMiner/                    Python backend
│  ├─ api_server.py
│  ├─ config/
│  └─ pubminer/
├─ docs/                        Notes and example inputs
├─ download/                    Downloaded and cached PMC/OA PDF content
├─ output/                      Exported CSV files and checkpoints
├─ db/                          Local data and support files
└─ README.md
```

## Workspace Conventions

Use the root directories with the following intent:

- Source code
  - `src/` for the Next.js frontend
  - `PubMiner/` for the FastAPI backend and Python package
  - `prisma/` for database schema and Prisma metadata
  - `public/` for frontend static assets
- Documentation and examples
- `docs/` for example inputs, notes, and future project docs
- Runtime artifacts
  - `download/` for PMC BioC cache and OA PDF cache
  - `output/` for exported CSV files and checkpoints
  - `db/` for local SQLite files, including persisted task and search-session state
- Local machine only
  - `.venv/`, `.env`, `.tmp/`, and local log files are environment-specific and should not be treated as source files

When adding new files, prefer:

- `docs/` for sample inputs, notes, or operational docs
- `src/` or `PubMiner/` for code that is part of the product
- `download/`, `output/`, or `db/` only for generated runtime data

## Setup

### 1. Frontend

Install dependencies from the project root:

```bash
pnpm install
```

Start the frontend:

```bash
pnpm dev
```

By default the frontend runs on:

- [http://localhost:3001](http://localhost:3001)

### 2. Backend

Create and activate a Python environment, then install backend dependencies.

Example:

```bash
cd PubMiner
pip install -r requirements.txt
```

Start the API server:

```bash
python api_server.py
```

By default the backend runs on:

- [http://localhost:8000](http://localhost:8000)

If you start the backend this way, set `NEXT_PUBLIC_API_URL=http://localhost:8000` in [/.env](/D:/Study/Project/PubMiner2/.env) before starting the Next.js frontend.

From the project root you can also use:

```powershell
.\start_backend.ps1
```

This script always uses [\.venv\Scripts\python.exe](/D:/Study/Project/PubMiner2/.venv/Scripts/python.exe), starts [api_server.py](/D:/Study/Project/PubMiner2/PubMiner/api_server.py) from the correct backend directory, and warns if port `8000` is already occupied.

### Environment Files

Recommended convention:

- use [\.env.example](/D:/Study/Project/PubMiner2/.env.example) as the template
- copy it to [/.env](/D:/Study/Project/PubMiner2/.env) on your machine
- keep real secrets only in `.env`
- do not commit `.env`

Current lookup behavior:

- the backend supports both root and backend-local env files for backward compatibility
- the effective priority is now:
  1. root `.env`
  2. `PubMiner/.env`
  3. root `.env.local`
  4. `PubMiner/.env.local`

Practical guidance:

- prefer putting `NCBI_EMAIL`, `NCBI_API_KEY`, `ZHIPU_API_KEY`, `UNPAYWALL_EMAIL`, and `NEXT_PUBLIC_API_URL` in the root [/.env](/D:/Study/Project/PubMiner2/.env)
- if both `.env` and `.env.local` exist, `.env` should now win
- the repository only ships the root [/.env.example](/D:/Study/Project/PubMiner2/.env.example) template now

### 3. Command Line Interface

The backend package now also supports direct CLI usage.

Run commands from [PubMiner](/D:/Study/Project/PubMiner2/PubMiner):

```powershell
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main --help
```

Available subcommands:

- `search`
  Search PubMed, persist a local search session, and preview the first loaded page
- `oa-check`
  Resolve legal OA PDF availability for PMIDs, a PMID file, or a saved search session
- `oa-download`
  Download legal OA PDFs with the same PMC-first strategy used by the web app
- `extract`
  Run extraction from PMIDs or a saved search session using the same persisted task/chunk flow as the web app
- `tasks`
  Inspect persisted extraction tasks or saved search sessions in local SQLite
- `pipeline`
  Run the older all-in-one CLI pipeline for backward compatibility

Common examples:

```powershell
# Create a saved search session
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main search -q "aging[tiab]" --max-results 20 --load-size 5

# Check OA PDF availability for a few PMIDs
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main oa-check --pmids 31452104 41876404 --limit 2

# Download OA PDFs and write a manifest
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main oa-download --session-id <search_session_id> --limit 10 --manifest-out ..\\output\\oa_manifest.json --zip-output ..\\output\\oa_pdfs.zip

# Run extraction against a saved search session
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main extract --session-id <search_session_id>

# Inspect local tasks and sessions
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main tasks --view tasks --limit 10
D:\Study\Project\PubMiner2\.venv\Scripts\python.exe -m pubminer.cli.main tasks --view sessions --limit 10
```

Notes:

- CLI and web extraction now share the same persisted task format in [db/pubminer_tasks.db](/D:/Study/Project/PubMiner2/db/pubminer_tasks.db)
- `extract` creates the same `task_id`, `article_report`, `chunk_report`, and `result_file` records that the task panel reads in the web app
- `oa-check` and `oa-download` can use `--query`, `--file`, `--session-id`, or inline `--pmids`

## Configuration

Backend configuration lives in:

- `PubMiner/config/default.yaml`

Important sections:

- `ncbi`
- `zhipu`
- `search`
- `download`
- `extraction`
- `output`
- `checkpoint`
- `oa_pdf`
- `database`

Example PMIDs for quick manual testing live in:

- `docs/examples/test_pmids.txt`

OA PDF benchmark for the fixed 10-article sample:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_oa_pdf.py
```

Optional variants:

```powershell
.\.venv\Scripts\python.exe .\scripts\benchmark_oa_pdf.py --method pmc
.\.venv\Scripts\python.exe .\scripts\benchmark_oa_pdf.py --method europepmc-ptpmcrender
.\.venv\Scripts\python.exe .\scripts\benchmark_oa_pdf.py --method europepmc-pdf-render
.\.venv\Scripts\python.exe .\scripts\benchmark_oa_pdf.py --concurrency 5 --timeout 60
```

## Security Note

The current `PubMiner/config/default.yaml` still contains plain-text API keys.

That is not a safe long-term setup.

Recommended next step:

1. move NCBI and Zhipu keys to environment variables
2. load them in the backend at startup
3. remove secrets from tracked config files

## CSV Output

Current export behavior:

- citation-related columns are omitted when citation fetching is disabled
- bibliographic metadata is ordered before LLM extraction fields
- output file names follow a stable pattern such as:

```text
pubminer_extract_20260313_153000_10articles.csv
pubminer_extract_20260313_153000_10articles_citations.csv
pubminer_extract_20260313_153000_10articles_2custom.csv
```

## Known Limitations

- very large searches still require manual `Load next ...` pagination after the first page
- automatic OA PDF checks are intentionally limited to the current visible page for responsiveness
- some PMC articles still require fallback full-text assembly
- repository-wide lint and type-check noise still exists in unrelated legacy or example areas
- the current full-project TypeScript check is still blocked by the existing `src/lib/db.ts` Prisma issue
- secret management still needs cleanup

## Recommended Next Steps

If you continue productizing this project, the most natural next steps are:

1. move secrets to environment variables
2. add optional background jobs for all-session OA PDF resolution
3. virtualize or further aggregate very large loaded result lists in the frontend
4. improve result table filtering and search
5. add automated backend and frontend regression tests
