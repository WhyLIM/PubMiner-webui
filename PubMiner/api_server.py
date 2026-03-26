# -*- coding: utf-8 -*-
"""
PubMiner API Server
FastAPI-based REST API for PubMiner functionality
"""

import os
import sys
import asyncio
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
import uvicorn
from fastapi.responses import FileResponse, Response

# Add parent directory to path to import pubminer
sys.path.insert(0, str(Path(__file__).parent))

from pubminer.core.config import Config
from pubminer.fetcher.pubmed_client import AsyncPubMedClient
from pubminer.downloader.pmc_bioc import BioCAPIClient
from pubminer.downloader.oa_pdf import OAPdfResolver
from pubminer.extractor.zhipu_client import ZhipuExtractor
from pubminer.extractor.schemas.base_info import BaseExtractionModel
from pubminer.extractor.schemas.custom import CustomFieldDefinition, DynamicSchemaBuilder
from pubminer.exporter.column_mapping import COLUMN_MAPPING
from pubminer.exporter.csv_writer import CSVExporter
from pubminer.core.logger import get_logger
from pubminer.core.task_store import SQLiteTaskStore
from pubminer.core.extraction_tasks import (
    build_task_id as build_persisted_task_id,
    create_extraction_task as create_persisted_extraction_task,
    run_extraction_task as run_persisted_extraction_task,
)

logger = get_logger("api")

# Initialize FastAPI app
app = FastAPI(
    title="PubMiner API",
    description="Medical Literature Mining API",
    version="0.1.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global config
config = None
task_store = None


# Request/Response Models
class SearchRequest(BaseModel):
    query: str
    max_results: int = 100
    offset: int = 0
    load_size: int = 50
    search_session_id: Optional[str] = None


class PMIDRequest(BaseModel):
    pmids: List[str]


class CustomFieldPayload(BaseModel):
    name: str
    description: str
    type: str = "text"
    enumValues: Optional[List[str]] = None


class ExtractionRequest(BaseModel):
    pmids: List[str] = Field(default_factory=list)
    custom_fields: Optional[List[CustomFieldPayload]] = None
    fetch_citations: bool = False  # Whether to fetch citation metadata
    search_session_id: Optional[str] = None
    scope: str = "selected"  # selected | all_matched


class RetryTaskRequest(BaseModel):
    pmids: Optional[List[str]] = None
    mode: str = "failed"  # failed | incomplete | all
    fetch_citations: Optional[bool] = None
    custom_fields: Optional[List[CustomFieldPayload]] = None


class OAPdfArticleRequest(BaseModel):
    pmid: str
    doi: Optional[str] = None
    pmcid: Optional[str] = None
    title: Optional[str] = None


class OAPdfResolveRequest(BaseModel):
    articles: List[OAPdfArticleRequest]
    unpaywall_email: Optional[str] = None


class OAPdfDownloadRequest(BaseModel):
    article: OAPdfArticleRequest
    unpaywall_email: Optional[str] = None


class OAPdfBatchDownloadRequest(BaseModel):
    articles: List[OAPdfArticleRequest]
    unpaywall_email: Optional[str] = None


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    result_file: Optional[str] = None
    fulltext_report: Optional[Dict[str, Any]] = None
    citation_report: Optional[Dict[str, Any]] = None
    extraction_report: Optional[Dict[str, Any]] = None
    article_report: Optional[List[Dict[str, Any]]] = None
    chunk_report: Optional[List[Dict[str, Any]]] = None


METADATA_COLUMNS = {
    "pmid", "pmcid", "doi", "title", "authors", "first_author", "affiliation",
    "journal", "j_abbrev", "issn", "journal_id", "pub_date", "year", "volume", "issue",
    "pages", "article_type", "publication_status", "language", "status", "last_revision",
    "has_fulltext", "cited_count", "references_count", "grant_list", "abstract", "keywords",
    "mesh_terms"
}
EXTRACTION_REQUIRED_COLUMNS = ["pmid", "pmcid", "doi", "title"]


def build_result_dataframe(file_path: Path, mode: str) -> pd.DataFrame:
    """Load and optionally filter result columns."""
    df = pd.read_csv(file_path, encoding="utf-8-sig").fillna("")

    if mode == "metadata":
        selected_columns = [col for col in df.columns if col in METADATA_COLUMNS]
        return df[selected_columns]

    if mode == "extraction":
        extraction_columns = [col for col in df.columns if col not in METADATA_COLUMNS]
        selected_columns = []
        for col in EXTRACTION_REQUIRED_COLUMNS + extraction_columns:
            if col in df.columns and col not in selected_columns:
                selected_columns.append(col)
        return df[selected_columns]

    return df


def build_export_basename(
    timestamp: str,
    article_count: int,
    fetch_citations: bool,
    custom_field_count: int,
) -> str:
    """Create a readable, stable export filename stem."""
    parts = [
        "pubminer",
        "extract",
        timestamp,
        f"{article_count}articles",
    ]
    if fetch_citations:
        parts.append("citations")
    if custom_field_count > 0:
        parts.append(f"{custom_field_count}custom")
    return "_".join(parts)


def chunk_items(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into fixed-size chunks."""
    if chunk_size <= 0:
        return [items]
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def stable_hash(value: str) -> str:
    """Hash a string into a stable cache key."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_search_session_id(query: str, max_results: int) -> str:
    """Create a stable-enough id for a persisted search session."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_hash = stable_hash(f"{query}|{max_results}|{timestamp}")[:10]
    return f"search_{timestamp}_{short_hash}"


def clamp_search_load_size(load_size: int, session_total: int) -> int:
    """Keep search page sizes bounded for responsive UI loads."""
    if session_total <= 0:
        return 0
    return max(1, min(load_size, 100, session_total))


def metadata_to_search_result(meta: Any) -> Dict[str, Any]:
    """Convert a metadata model into the frontend search result shape."""
    meta_dict = meta.model_dump() if hasattr(meta, "model_dump") else meta.dict()
    return {
        "pmid": meta_dict.get("pmid"),
        "title": meta_dict.get("title"),
        "authors": meta_dict.get("authors", []),
        "firstAuthor": meta_dict.get("first_author", ""),
        "affiliation": meta_dict.get("affiliation", ""),
        "journal": meta_dict.get("journal"),
        "year": str(meta_dict.get("year") or ""),
        "articleType": meta_dict.get("article_type", ""),
        "publicationStatus": meta_dict.get("publication_status", ""),
        "language": meta_dict.get("language", ""),
        "doi": meta_dict.get("doi"),
        "abstract": meta_dict.get("abstract", ""),
        "hasFullText": meta_dict.get("pmcid") is not None,
        "pmcid": meta_dict.get("pmcid"),
    }


def build_schema_hash(schema_model: Any) -> str:
    """Build a stable hash for an extraction schema."""
    schema_json = schema_model.model_json_schema()
    canonical = json.dumps(schema_json, sort_keys=True, ensure_ascii=False)
    return stable_hash(canonical)


def create_empty_fulltext_report(pmc_candidates: int = 0) -> Dict[str, Any]:
    """Build the default full-text report shape."""
    return {
        "pmc_candidates": pmc_candidates,
        "downloaded": 0,
        "failed": 0,
        "fallback_used": 0,
        "cache_hits": 0,
        "cache_misses": pmc_candidates,
        "failure_counts": {},
        "failure_labels": {},
        "failed_items": [],
        "items": [],
    }


def merge_fulltext_reports(
    accumulated: Dict[str, Any],
    chunk_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge per-chunk full-text reports into a campaign-wide summary."""
    merged = {
        "pmc_candidates": accumulated.get("pmc_candidates", 0) + chunk_report.get("pmc_candidates", 0),
        "downloaded": accumulated.get("downloaded", 0) + chunk_report.get("downloaded", 0),
        "failed": accumulated.get("failed", 0) + chunk_report.get("failed", 0),
        "fallback_used": accumulated.get("fallback_used", 0) + chunk_report.get("fallback_used", 0),
        "cache_hits": accumulated.get("cache_hits", 0) + chunk_report.get("cache_hits", 0),
        "failure_counts": dict(accumulated.get("failure_counts", {})),
        "failure_labels": dict(accumulated.get("failure_labels", {})),
        "failed_items": list(accumulated.get("failed_items", [])),
        "items": list(accumulated.get("items", [])),
    }
    merged["cache_misses"] = max(merged["pmc_candidates"] - merged["cache_hits"], 0)

    for key, value in chunk_report.get("failure_counts", {}).items():
        merged["failure_counts"][key] = merged["failure_counts"].get(key, 0) + value
    merged["failure_labels"].update(chunk_report.get("failure_labels", {}))
    merged["failed_items"].extend(chunk_report.get("failed_items", []))
    merged["items"].extend(chunk_report.get("items", []))
    return merged


def create_empty_extraction_report() -> Dict[str, Any]:
    """Build the default extraction report shape."""
    return {
        "attempted": 0,
        "cached_hits": 0,
        "fresh_runs": 0,
        "success": 0,
        "failed": 0,
    }


def merge_extraction_reports(
    accumulated: Dict[str, Any],
    *,
    attempted: int,
    cached_hits: int,
    fresh_runs: int,
    success: int,
    failed: int,
) -> Dict[str, Any]:
    """Accumulate per-chunk extraction statistics."""
    merged = dict(accumulated)
    merged["attempted"] = merged.get("attempted", 0) + attempted
    merged["cached_hits"] = merged.get("cached_hits", 0) + cached_hits
    merged["fresh_runs"] = merged.get("fresh_runs", 0) + fresh_runs
    merged["success"] = merged.get("success", 0) + success
    merged["failed"] = merged.get("failed", 0) + failed
    return merged


def apply_citation_data(
    metadata_list: List[Any],
    citation_data: Dict[str, Dict[str, Any]],
) -> None:
    """Merge fetched citation data into metadata records in place."""
    for metadata in metadata_list:
        pmid = getattr(metadata, "pmid", None)
        if not pmid or pmid not in citation_data:
            continue

        data = citation_data[pmid]
        metadata.cited_count = data.get("cited_count", 0)
        metadata.cited_by = data.get("cited_by", [])
        metadata.references_count = data.get("references_count", 0)
        metadata.references = data.get("references", [])


def select_retry_pmids(task: Dict[str, Any], mode: str) -> List[str]:
    """Select PMIDs eligible for retry from a persisted task payload."""
    articles = task.get("article_report") or []
    if mode == "all":
        return [item["pmid"] for item in articles if item.get("pmid")]

    if mode == "incomplete":
        return [
            item["pmid"]
            for item in articles
            if item.get("pmid") and item.get("result_status") != "full_table"
        ]

    failed_fulltext_states = {"request_failed", "parse_error", "empty_content"}
    failed_extraction_states = {"failed", "missing"}
    return [
        item["pmid"]
        for item in articles
        if item.get("pmid") and (
            item.get("fulltext_status") in failed_fulltext_states
            or item.get("extraction_status") in failed_extraction_states
        )
    ]


def build_oa_pdf_resolver(unpaywall_email: Optional[str] = None) -> OAPdfResolver:
    """Create a resolver using the active configuration."""
    return OAPdfResolver(
        timeout=config.oa_pdf.timeout,
        max_retries=config.oa_pdf.max_retries,
        prefer_pmc=config.oa_pdf.prefer_pmc,
        strict_oa=config.oa_pdf.strict_oa,
        cache_dir=config.oa_pdf.cache_dir,
        cache_only_when_license_known=config.oa_pdf.cache_only_when_license_known,
        unpaywall_email=unpaywall_email or config.oa_pdf.unpaywall_email,
        enable_pmc=config.oa_pdf.enable_pmc,
        enable_unpaywall=config.oa_pdf.enable_unpaywall,
        enable_europepmc=config.oa_pdf.enable_europepmc,
        resolve_concurrency=config.oa_pdf.resolve_concurrency,
    )


def get_task_store() -> SQLiteTaskStore:
    """Return the initialized task store."""
    if task_store is None:
        raise RuntimeError("Task store is not initialized")
    return task_store


def persist_task(
    task_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    message: Optional[str] = None,
    result_file: Optional[str] = None,
    fulltext_report: Optional[Dict[str, Any]] = None,
    citation_report: Optional[Dict[str, Any]] = None,
    extraction_report: Optional[Dict[str, Any]] = None,
    article_report: Optional[List[Dict[str, Any]]] = None,
    chunk_report: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Persist task-level and article-level state updates."""
    store = get_task_store()
    store.update_task(
        task_id,
        status=status,
        progress=progress,
        message=message,
        result_file=result_file,
        fulltext_report=fulltext_report,
        citation_report=citation_report,
        extraction_report=extraction_report,
    )
    if article_report is not None:
        store.replace_articles(task_id, article_report)
    if chunk_report is not None:
        store.replace_chunks(task_id, chunk_report)


@app.on_event("startup")
async def startup_event():
    """Initialize configuration on startup"""
    global config, task_store
    config_path = Path(__file__).parent / "config" / "default.yaml"
    config = Config.from_yaml(str(config_path))
    config.ensure_directories()
    task_store = SQLiteTaskStore(config.database.path)
    logger.info("PubMiner API server started")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "PubMiner API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/api/search")
async def search_pubmed(request: SearchRequest):
    """Search PubMed for articles"""
    try:
        client = AsyncPubMedClient(
            email=config.ncbi.email,
            api_key=config.ncbi.api_key,
            tool_name=config.ncbi.tool_name,
            rate_limit=config.ncbi.rate_limit
        )

        if request.search_session_id:
            search_session = get_task_store().get_search_session(request.search_session_id)
            if search_session is None:
                raise HTTPException(status_code=404, detail="Search session not found")
            session_id = search_session["session_id"]
            query = search_session["query"]
            session_pmids = search_session["pmids"]
            total_available = search_session["total_available"]
            scope_limit = search_session["scope_limit"]
        else:
            search_result = await client.search(
                request.query,
                max_results=request.max_results,
                offset=0,
            )
            session_pmids = search_result["pmids"]
            total_available = search_result["total_count"]
            scope_limit = request.max_results
            query = request.query
            session_id = build_search_session_id(request.query, request.max_results)
            get_task_store().save_search_session(
                session_id=session_id,
                source="query",
                query=request.query,
                total_available=total_available,
                scope_limit=scope_limit,
                pmids=session_pmids,
            )

        safe_offset = max(0, request.offset)
        safe_load_size = clamp_search_load_size(request.load_size, len(session_pmids))
        page_pmids = session_pmids[safe_offset:safe_offset + safe_load_size]
        metadata_list = await client.fetch_metadata(page_pmids, include_citations=False)
        results = [metadata_to_search_result(meta) for meta in metadata_list]

        return {
            "success": True,
            "query": query,
            "total": len(results),
            "total_available": total_available,
            "session_total": len(session_pmids),
            "search_session_id": session_id,
            "offset": safe_offset,
            "load_size": safe_load_size,
            "returned_count": len(results),
            "has_more": safe_offset + len(results) < len(session_pmids),
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fetch-metadata")
async def fetch_metadata(request: PMIDRequest):
    """Fetch metadata for given PMIDs"""
    try:
        client = AsyncPubMedClient(
            email=config.ncbi.email,
            api_key=config.ncbi.api_key,
            tool_name=config.ncbi.tool_name,
            rate_limit=config.ncbi.rate_limit
        )

        metadata_list = await client.fetch_metadata(request.pmids, include_citations=False)

        results = []
        for meta in metadata_list:
            meta_dict = meta.model_dump() if hasattr(meta, 'model_dump') else meta.dict()
            results.append(meta_dict)

        return {
            "success": True,
            "total": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Fetch metadata error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/resolve-oa-pdf")
async def resolve_oa_pdf(request: OAPdfResolveRequest):
    """Resolve legal OA PDF candidates for the requested articles."""
    if not config.oa_pdf.enabled:
        raise HTTPException(status_code=400, detail="OA PDF feature is disabled")

    try:
        resolver = build_oa_pdf_resolver(request.unpaywall_email)
        resolutions = await resolver.resolve_many([article.model_dump() for article in request.articles])
        return {
            "success": True,
            "results": [resolution.model_dump() for resolution in resolutions],
        }
    except Exception as e:
        logger.error(f"OA PDF resolve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-oa-pdf")
async def download_oa_pdf(request: OAPdfDownloadRequest):
    """Download the best legal OA PDF for an article and return the file."""
    if not config.oa_pdf.enabled:
        raise HTTPException(status_code=400, detail="OA PDF feature is disabled")

    try:
        resolver = build_oa_pdf_resolver(request.unpaywall_email)
        record = await resolver.download_best(request.article.model_dump())
        if record.status != "downloaded" or not record.local_path:
            raise HTTPException(status_code=404, detail=record.error or "No OA PDF was downloaded")

        file_path = Path(record.local_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Downloaded file was not found on disk")

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=record.filename or file_path.name,
            headers={
                "X-OA-PDF-Source": record.source,
                "X-OA-PDF-License": record.license or "",
                "X-OA-PDF-Cached": str(record.cached).lower(),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OA PDF download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-oa-pdfs")
async def download_oa_pdfs(request: OAPdfBatchDownloadRequest):
    """Download multiple legal OA PDFs and return them as a zip archive."""
    if not config.oa_pdf.enabled:
        raise HTTPException(status_code=400, detail="OA PDF feature is disabled")

    if not request.articles:
        raise HTTPException(status_code=400, detail="No articles were provided")

    try:
        article_payloads = [article.model_dump() for article in request.articles]
        pmc_first_articles = [article for article in article_payloads if article.get("pmcid")]
        fallback_only_articles = [article for article in article_payloads if not article.get("pmcid")]
        records_by_pmid: Dict[str, Any] = {}

        if pmc_first_articles:
            fast_resolver = OAPdfResolver(
                timeout=config.oa_pdf.pmc_timeout,
                max_retries=config.oa_pdf.pmc_max_retries,
                prefer_pmc=config.oa_pdf.prefer_pmc,
                strict_oa=config.oa_pdf.strict_oa,
                cache_dir=config.oa_pdf.cache_dir,
                cache_only_when_license_known=config.oa_pdf.cache_only_when_license_known,
                unpaywall_email=None,
                enable_pmc=config.oa_pdf.enable_pmc,
                enable_unpaywall=False,
                enable_europepmc=False,
                resolve_concurrency=config.oa_pdf.resolve_concurrency,
            )
            fast_records = await fast_resolver.download_many(
                pmc_first_articles,
                concurrency=config.oa_pdf.pmc_download_concurrency,
            )
            for record in fast_records:
                records_by_pmid[record.pmid] = record

            retry_articles = [
                article
                for article in pmc_first_articles
                if records_by_pmid.get(article.get("pmid")) is not None
                and records_by_pmid[article.get("pmid")].status != "downloaded"
            ]
        else:
            retry_articles = []

        retry_articles.extend(fallback_only_articles)

        if retry_articles:
            fallback_resolver = OAPdfResolver(
                timeout=config.oa_pdf.fallback_timeout,
                max_retries=config.oa_pdf.fallback_max_retries,
                prefer_pmc=config.oa_pdf.prefer_pmc,
                strict_oa=config.oa_pdf.strict_oa,
                cache_dir=config.oa_pdf.cache_dir,
                cache_only_when_license_known=config.oa_pdf.cache_only_when_license_known,
                unpaywall_email=request.unpaywall_email or config.oa_pdf.unpaywall_email,
                enable_pmc=config.oa_pdf.enable_pmc,
                enable_unpaywall=config.oa_pdf.enable_unpaywall,
                enable_europepmc=config.oa_pdf.enable_europepmc,
                resolve_concurrency=config.oa_pdf.resolve_concurrency,
            )
            fallback_records = await fallback_resolver.download_many(
                retry_articles,
                concurrency=config.oa_pdf.fallback_download_concurrency,
            )
            for record in fallback_records:
                records_by_pmid[record.pmid] = record

        records = [records_by_pmid[article["pmid"]] for article in article_payloads if article.get("pmid") in records_by_pmid]
        successful_records = [record for record in records if record.status == "downloaded" and record.local_path]

        if not successful_records:
            raise HTTPException(status_code=404, detail="No OA PDFs were downloaded for the selected articles")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            zip_path = Path(tmp_file.name)

        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for record in successful_records:
                file_path = Path(record.local_path)
                if file_path.exists():
                    archive.write(file_path, arcname=record.filename or file_path.name)
            archive.writestr(
                "manifest.json",
                json.dumps([record.model_dump() for record in records], ensure_ascii=False, indent=2),
            )

        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=f"oa_pdfs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            headers={
                "X-OA-PDF-Count": str(len(successful_records)),
                "X-OA-PDF-Failed": str(len(records) - len(successful_records)),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OA PDF batch download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/extract")
async def extract_information(request: ExtractionRequest, background_tasks: BackgroundTasks):
    """Extract structured information from articles"""
    if request.scope == "all_matched":
        if not request.search_session_id:
            raise HTTPException(status_code=400, detail="search_session_id is required for all_matched extraction")
        search_session = get_task_store().get_search_session(request.search_session_id)
        if search_session is None:
            raise HTTPException(status_code=404, detail="Search session not found")
        effective_pmids = search_session["pmids"]
        task_query = search_session["query"] or "Matched Articles"
    else:
        effective_pmids = request.pmids
        task_query = "Selected Articles"

    if not effective_pmids:
        raise HTTPException(status_code=400, detail="No PMIDs were provided for extraction")

    task_id = create_persisted_extraction_task(
        get_task_store(),
        pmids=effective_pmids,
        custom_fields=request.custom_fields,
        fetch_citations=request.fetch_citations,
        search_session_id=request.search_session_id,
        scope=request.scope,
        task_id=build_persisted_task_id(),
    )

    # Add to background tasks
    background_tasks.add_task(
        run_extraction_task,
        task_id,
        effective_pmids,
        request.custom_fields,
        request.fetch_citations
    )

    return {
        "success": True,
        "task_id": task_id,
        "article_count": len(effective_pmids),
        "query": task_query,
        "message": "Extraction task started"
    }


async def run_extraction_task(
    task_id: str,
    pmids: List[str],
    custom_fields: Optional[List[CustomFieldPayload]],
    fetch_citations: bool = False
):
    """Background task wrapper that delegates to the shared task runner."""
    await run_persisted_extraction_task(
        config=config,
        store=get_task_store(),
        task_id=task_id,
        pmids=pmids,
        custom_fields=custom_fields,
        fetch_citations=fetch_citations,
    )


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get task status"""
    task = get_task_store().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@app.post("/api/tasks/{task_id}/retry")
async def retry_task_articles(task_id: str, request: RetryTaskRequest, background_tasks: BackgroundTasks):
    """Retry selected articles from a previous task as a new persisted task."""
    source_task = get_task_store().get_task(task_id)
    if source_task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    source_payload = source_task.get("request_payload") or {}
    retry_pmids = request.pmids or select_retry_pmids(source_task, request.mode)
    retry_pmids = [pmid for pmid in retry_pmids if pmid]

    if not retry_pmids:
        raise HTTPException(status_code=400, detail="No PMIDs matched the retry selection")

    custom_fields_payload = request.custom_fields
    if custom_fields_payload is None:
        custom_fields_payload = [
            CustomFieldPayload(**field)
            for field in source_payload.get("custom_fields", [])
        ]

    fetch_citations = (
        request.fetch_citations
        if request.fetch_citations is not None
        else bool(source_payload.get("fetch_citations", False))
    )

    retry_task_id = create_persisted_extraction_task(
        get_task_store(),
        pmids=retry_pmids,
        custom_fields=custom_fields_payload,
        fetch_citations=fetch_citations,
        retry_of=task_id,
        task_id=f"{task_id}_retry_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    background_tasks.add_task(
        run_extraction_task,
        retry_task_id,
        retry_pmids,
        custom_fields_payload,
        fetch_citations,
    )

    return {
        "success": True,
        "task_id": retry_task_id,
        "article_count": len(retry_pmids),
        "message": f"Retry task started for {len(retry_pmids)} articles",
    }


@app.get("/api/results/{filename}/preview")
async def preview_result_file(filename: str, limit: int = 20, mode: str = "all"):
    """Preview result file content"""
    file_path = Path(config.output.directory) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    safe_limit = max(1, min(limit, 100))

    try:
        df = build_result_dataframe(file_path, mode)
        preview_df = df.head(safe_limit)

        return {
            "filename": filename,
            "mode": mode,
            "columns": preview_df.columns.tolist(),
            "rows": preview_df.to_dict(orient="records"),
            "preview_rows": len(preview_df),
            "total_rows": len(df),
        }
    except Exception as e:
        logger.error(f"Preview result error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/results/{filename}")
async def get_result_file(filename: str, mode: str = "all"):
    """Download result file"""
    file_path = Path(config.output.directory) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if mode == "all":
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='text/csv'
        )

    try:
        df = build_result_dataframe(file_path, mode)
        csv_content = df.to_csv(index=False, encoding="utf-8-sig")
        mode_suffix = {
            "metadata": "metadata",
            "extraction": "llm-fields",
            "all": "full-table",
        }.get(mode, mode)
        derived_name = f"{Path(filename).stem}_{mode_suffix}.csv"
        return Response(
            content=csv_content.encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{derived_name}"'}
        )
    except Exception as e:
        logger.error(f"Download result error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
