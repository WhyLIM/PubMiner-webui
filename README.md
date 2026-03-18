# PubMiner

PubMiner is a literature mining workspace for PubMed and PMC.

It combines:

- a `Next.js` frontend for search, article review, task monitoring, and result preview
- a `FastAPI` backend for PubMed retrieval, PMC full-text download, LLM extraction, and CSV export

The current workflow is:

1. Search PubMed or paste PMIDs
2. Review article metadata and summary charts
3. Select articles
4. Configure LLM extraction fields
5. Run extraction tasks
6. Preview and download CSV outputs

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
- incremental loading for search results
- metadata review before extraction
- article filtering and selection
- PubMed-style result statistics, including year distribution

### Extraction Workflow

- search and extraction are separated into distinct steps
- built-in extraction schema for common literature fields
- custom extraction field support
- optional citation fetching
- PMC full-text retrieval with structured section parsing
- fallback full-text assembly when section parsing is weak
- article-level extraction status tracking

### Task Diagnostics

- task queue and task detail panel
- full-text download report
- fallback usage report
- cache hit reporting
- citation status reporting
- article mapping from search result to final output row

### Result Handling

- preview extracted CSV data in the UI
- switch between `Metadata`, `LLM`, and `Full` preview modes
- grouped visible-column controls
- multiple CSV download modes:
  - metadata only
  - LLM fields only
  - full table

## Retrieval Pipeline

The backend uses the following retrieval flow:

1. `Entrez.esearch`
   Find PMIDs from a PubMed query
2. `Entrez.efetch`
   Fetch PubMed XML metadata for those PMIDs
3. optional `Entrez.elink`
   Fetch citation and reference links when enabled
4. `PMC BioC API`
   Download full text for records with a PMCID
5. section parser + fallback
   Build usable extraction text from PMC content
6. `ZhipuExtractor`
   Extract structured fields with a schema-driven prompt
7. `CSVExporter`
   Merge metadata and LLM results into ordered CSV output

## Recent Engineering Improvements

This project has already been improved beyond the initial scaffold. Notable changes include:

- search preview and LLM extraction split into separate UX stages
- dynamic custom extraction fields wired end-to-end
- result preview in the frontend
- article-level mapping between search results and extraction outputs
- PMC full-text caching in `download/pmc_cache`
- citation fetching enabled only when requested
- citation fetching parallelized with the main extraction flow
- enhanced section parsing with fallback logic
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

Example PMIDs for quick manual testing live in:

- `docs/examples/test_pmids.txt`

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

- task storage is still in memory and is not persistent across backend restarts
- some PMC articles still require fallback full-text assembly
- repository-wide lint and type-check noise still exists in unrelated legacy or example areas
- secret management still needs cleanup

## Recommended Next Steps

If you continue productizing this project, the most natural next steps are:

1. persist task state
2. move secrets to environment variables
3. add single-article retry flows
4. improve result table filtering and search
5. add automated backend and frontend regression tests
