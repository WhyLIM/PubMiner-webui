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
from pydantic import BaseModel
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


class PMIDRequest(BaseModel):
    pmids: List[str]


class CustomFieldPayload(BaseModel):
    name: str
    description: str
    type: str = "text"
    enumValues: Optional[List[str]] = None


class ExtractionRequest(BaseModel):
    pmids: List[str]
    custom_fields: Optional[List[CustomFieldPayload]] = None
    fetch_citations: bool = False  # Whether to fetch citation metadata


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

        # Search and fetch metadata
        search_result = await client.search(
            request.query,
            max_results=request.max_results,
            offset=request.offset,
        )
        pmids = search_result["pmids"]
        metadata_list = await client.fetch_metadata(pmids, include_citations=False)

        # Convert to dict
        results = []
        for meta in metadata_list:
            meta_dict = meta.model_dump() if hasattr(meta, 'model_dump') else meta.dict()
            results.append({
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
                "pmcid": meta_dict.get("pmcid")
            })

        return {
            "success": True,
            "query": request.query,
            "total": len(results),
            "total_available": search_result["total_count"],
            "offset": request.offset,
            "returned_count": len(results),
            "has_more": request.offset + len(results) < search_result["total_count"],
            "results": results
        }

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
                timeout=config.oa_pdf.timeout,
                max_retries=config.oa_pdf.max_retries,
                prefer_pmc=config.oa_pdf.prefer_pmc,
                strict_oa=config.oa_pdf.strict_oa,
                cache_dir=config.oa_pdf.cache_dir,
                cache_only_when_license_known=config.oa_pdf.cache_only_when_license_known,
                unpaywall_email=None,
                enable_pmc=config.oa_pdf.enable_pmc,
                enable_unpaywall=False,
                enable_europepmc=False,
            )
            fast_records = await fast_resolver.download_many(pmc_first_articles, concurrency=3)
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
            fallback_resolver = build_oa_pdf_resolver(request.unpaywall_email)
            fallback_records = await fallback_resolver.download_many(retry_articles, concurrency=3)
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
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Initialize task status in the local task database.
    get_task_store().create_task(
        task_id,
        request.pmids,
        request_payload={
            "pmids": request.pmids,
            "custom_fields": [field.model_dump() for field in request.custom_fields or []],
            "fetch_citations": request.fetch_citations,
        },
    )

    # Add to background tasks
    background_tasks.add_task(
        run_extraction_task,
        task_id,
        request.pmids,
        request.custom_fields,
        request.fetch_citations
    )

    return {
        "success": True,
        "task_id": task_id,
        "message": "Extraction task started"
    }


async def run_extraction_task(
    task_id: str,
    pmids: List[str],
    custom_fields: Optional[List[CustomFieldPayload]],
    fetch_citations: bool = False
):
    """Background task for extraction"""
    chunk_report: List[Dict[str, Any]] = []
    try:
        persist_task(task_id, status="running", message="Fetching metadata...", progress=0.1)

        # Fetch metadata
        client = AsyncPubMedClient(
            email=config.ncbi.email,
            api_key=config.ncbi.api_key,
            tool_name=config.ncbi.tool_name,
            rate_limit=config.ncbi.rate_limit
        )

        citation_task = None
        citation_client = None

        # Fetch metadata first, then optionally fetch citations in parallel
        if fetch_citations:
            metadata_list = await client.fetch_metadata(pmids, include_citations=False)
            citation_client = AsyncPubMedClient(
                email=config.ncbi.email,
                api_key=config.ncbi.api_key,
                tool_name=config.ncbi.tool_name,
                rate_limit=config.ncbi.rate_limit
            )
            citation_report = {
                "enabled": True,
                "status": "running",
                "message": "Citation data is being fetched in parallel.",
                "cited_by_status": "pending",
                "references_status": "pending",
                "cited_by_total": 0,
                "references_total": 0,
            }
            persist_task(task_id, citation_report=citation_report)
            citation_task = asyncio.create_task(citation_client.fetch_citation_data(pmids))
        else:
            metadata_list = await client.fetch_metadata(pmids, include_citations=False)
            citation_report = {
                "enabled": False,
                "status": "disabled",
                "message": "Citation fetching was turned off for this task.",
                "cited_by_status": "disabled",
                "references_status": "disabled",
                "cited_by_total": 0,
                "references_total": 0,
            }
            persist_task(task_id, citation_report=citation_report)

        article_report: Dict[str, Dict[str, Any]] = {}
        for metadata in metadata_list:
            article_report[metadata.pmid] = {
                "pmid": metadata.pmid,
                "pmcid": metadata.pmcid,
                "title": metadata.title,
                "journal": metadata.journal,
                "year": metadata.year,
                "has_fulltext": bool(metadata.pmcid),
                "citation_status": "pending" if fetch_citations else "disabled",
                "fulltext_status": "pending" if metadata.pmcid else "no_pmc",
                "oa_pdf_status": "pending",
                "extraction_status": "pending" if metadata.pmcid else "skipped",
                "result_status": "pending",
                "error": "",
            }
        persist_task(task_id, article_report=list(article_report.values()))

        chunk_size = config.extraction.task_chunk_size
        metadata_chunks = chunk_items(metadata_list, chunk_size)
        total_chunks = max(len(metadata_chunks), 1)
        aggregated_fulltext_report = create_empty_fulltext_report()
        aggregated_extraction_report = create_empty_extraction_report()
        extraction_results: List[Dict[str, Any]] = []
        chunk_report = [
            {
                "chunk_index": index,
                "article_count": len(metadata_chunk),
                "status": "pending",
                "fulltext_downloaded": 0,
                "extraction_success": 0,
                "extraction_failed": 0,
                "cached_hits": 0,
                "pmids": [metadata.pmid for metadata in metadata_chunk],
                "message": "Waiting to start",
            }
            for index, metadata_chunk in enumerate(metadata_chunks, start=1)
        ]
        persist_task(task_id, chunk_report=chunk_report)

        # Build extraction schema once and reuse it across chunks.

        schema_model = BaseExtractionModel
        custom_output_columns: List[str] = []
        if custom_fields:
            custom_definitions = []
            for field in custom_fields:
                field_type = "str"
                if field.type == "number":
                    field_type = "float"
                elif field.type == "enum":
                    field_type = "enum"

                custom_definitions.append(
                    CustomFieldDefinition(
                        name=field.name,
                        description=field.description,
                        field_type=field_type,
                        enum_values=field.enumValues or [],
                    )
                )
                custom_output_columns.append(COLUMN_MAPPING.get(field.name, field.name))

            schema_model = DynamicSchemaBuilder.create_custom_model(
                custom_fields=custom_definitions,
                model_name=f"Task{task_id.replace('-', '_')}ExtractionModel",
            )

        downloader = BioCAPIClient(
            keep_sections=config.download.sections,
            timeout=config.download.timeout,
            max_retries=config.download.max_retries,
            cache_dir=config.download.cache_dir,
        )
        extractor = ZhipuExtractor(
            api_key=config.zhipu.api_key,
            model=config.zhipu.model,
            temperature=config.zhipu.temperature,
            max_retries=config.extraction.max_retries,
            use_coding_plan=config.zhipu.use_coding_plan
        )
        extraction_schema_hash = build_schema_hash(schema_model)
        active_task_store = get_task_store()
        had_chunk_failures = False

        for chunk_index, metadata_chunk in enumerate(metadata_chunks, start=1):
            chunk_pmids = [metadata.pmid for metadata in metadata_chunk]
            chunk_message = f"Processing chunk {chunk_index}/{total_chunks} ({len(metadata_chunk)} articles)"
            chunk_entry = chunk_report[chunk_index - 1]
            chunk_entry["status"] = "running"
            chunk_entry["message"] = chunk_message
            persist_task(
                task_id,
                message=chunk_message,
                progress=0.1 + (0.7 * ((chunk_index - 1) / total_chunks)),
                chunk_report=chunk_report,
            )
            try:
                pmcids = [m.pmcid for m in metadata_chunk if m.pmcid]
                pmids_for_download = [m.pmid for m in metadata_chunk if m.pmcid]
                chunk_fulltext_docs = []

                if pmcids:
                    chunk_fulltext_docs, chunk_fulltext_report = await downloader.batch_download_with_report(
                        pmcids,
                        pmids_for_download,
                    )
                    aggregated_fulltext_report = merge_fulltext_reports(aggregated_fulltext_report, chunk_fulltext_report)
                else:
                    chunk_fulltext_report = create_empty_fulltext_report()

                chunk_entry["fulltext_downloaded"] = len(chunk_fulltext_docs)
                persist_task(task_id, fulltext_report=aggregated_fulltext_report)

                for metadata in metadata_chunk:
                    if not metadata.pmcid:
                        article_report[metadata.pmid]["fulltext_status"] = "no_pmc"
                        article_report[metadata.pmid]["extraction_status"] = "skipped"
                        article_report[metadata.pmid]["result_status"] = "metadata_only"

                for item in chunk_fulltext_report.get("items", []):
                    pmid = item.get("pmid")
                    if not pmid or pmid not in article_report:
                        continue
                    article_report[pmid]["fulltext_status"] = item.get("reason", item.get("status", "unknown"))
                    article_report[pmid]["error"] = item.get("message", "")

                for doc in chunk_fulltext_docs:
                    if doc.pmid in article_report:
                        article_report[doc.pmid]["fulltext_status"] = "ready"
                        article_report[doc.pmid]["error"] = ""

                if chunk_fulltext_docs:
                    cached_results: List[Dict[str, Any]] = []
                    docs_to_extract = []
                    docs_by_pmid = {doc.pmid: doc for doc in chunk_fulltext_docs}
                    for doc in chunk_fulltext_docs:
                        text_hash = stable_hash(doc.filtered_text or "")
                        cached_result = active_task_store.get_extraction_cache(
                            pmid=doc.pmid,
                            model_name=extractor.model,
                            schema_hash=extraction_schema_hash,
                            text_hash=text_hash,
                        )
                        if cached_result is not None:
                            cached_result["pmid"] = doc.pmid
                            cached_results.append(cached_result)
                        else:
                            docs_to_extract.append(doc)

                    chunk_extraction_results: List[Dict[str, Any]] = list(cached_results)
                    if docs_to_extract:
                        fresh_results = await extractor.batch_extract(
                            docs_to_extract,
                            schema_model,
                            concurrency=config.extraction.concurrency
                        )
                        for result in fresh_results:
                            if "error" not in result and result.get("pmid"):
                                matching_doc = docs_by_pmid.get(result.get("pmid"))
                                if matching_doc is not None:
                                    active_task_store.put_extraction_cache(
                                        pmid=matching_doc.pmid,
                                        model_name=extractor.model,
                                        schema_hash=extraction_schema_hash,
                                        text_hash=stable_hash(matching_doc.filtered_text or ""),
                                        result=result,
                                    )
                        chunk_extraction_results.extend(fresh_results)

                    extraction_results.extend(chunk_extraction_results)
                    chunk_successes = sum(1 for result in chunk_extraction_results if "error" not in result)
                    chunk_failures = len(chunk_extraction_results) - chunk_successes
                    chunk_entry["cached_hits"] = len(cached_results)
                    chunk_entry["extraction_success"] = chunk_successes
                    chunk_entry["extraction_failed"] = chunk_failures
                    aggregated_extraction_report = merge_extraction_reports(
                        aggregated_extraction_report,
                        attempted=len(chunk_fulltext_docs),
                        cached_hits=len(cached_results),
                        fresh_runs=len(docs_to_extract),
                        success=chunk_successes,
                        failed=chunk_failures,
                    )
                    persist_task(task_id, extraction_report=aggregated_extraction_report)
                    extraction_by_pmid = {result.get("pmid"): result for result in chunk_extraction_results}

                    for doc in chunk_fulltext_docs:
                        item = article_report.get(doc.pmid)
                        if item is None:
                            continue

                        result = extraction_by_pmid.get(doc.pmid)
                        if not result:
                            item["extraction_status"] = "missing"
                            item["result_status"] = "metadata_only"
                            continue

                        if "error" in result:
                            item["extraction_status"] = "failed"
                            item["result_status"] = "metadata_only"
                            item["error"] = str(result.get("error", ""))
                        else:
                            item["extraction_status"] = "success"
                            item["result_status"] = "full_table"
                else:
                    for metadata in metadata_chunk:
                        item = article_report[metadata.pmid]
                        if item["fulltext_status"] != "ready":
                            item["extraction_status"] = "skipped"
                            item["result_status"] = "metadata_only"

                chunk_entry["status"] = "completed"
                chunk_entry["message"] = (
                    f"Completed with {chunk_entry['fulltext_downloaded']} full text, "
                    f"{chunk_entry['extraction_success']} extraction success, "
                    f"{chunk_entry['cached_hits']} cache hits"
                )
            except Exception as chunk_error:
                had_chunk_failures = True
                logger.error(f"Chunk {chunk_index} failed in task {task_id}: {chunk_error}")
                if "Zhipu API authentication failed" in str(chunk_error):
                    raise
                chunk_entry["status"] = "failed"
                chunk_entry["message"] = str(chunk_error)
                for metadata in metadata_chunk:
                    item = article_report.get(metadata.pmid)
                    if item is None:
                        continue
                    if item["fulltext_status"] == "pending":
                        item["fulltext_status"] = "request_failed" if metadata.pmcid else "no_pmc"
                    if item["extraction_status"] in {"pending", "skipped"} and metadata.pmcid:
                        item["extraction_status"] = "failed"
                    if item["result_status"] == "pending":
                        item["result_status"] = "metadata_only"
                    item["error"] = str(chunk_error)

            persist_task(
                task_id,
                article_report=list(article_report.values()),
                extraction_report=aggregated_extraction_report,
                progress=0.1 + (0.7 * (chunk_index / total_chunks)),
                chunk_report=chunk_report,
            )

        if aggregated_fulltext_report.get("pmc_candidates", 0) == 0:
            logger.warning("No articles with PMC full text available, skipping LLM extraction")

        if citation_task and citation_client:
            persist_task(task_id, message="Finalizing citation data...")
            citation_data = await citation_task
            apply_citation_data(metadata_list, citation_data)
            for item in article_report.values():
                item["citation_status"] = "success"
            persist_task(task_id, citation_report=citation_client.last_citation_report)
            persist_task(task_id, article_report=list(article_report.values()))

        persist_task(task_id, message="Exporting results...", progress=0.9)

        # Export results
        output_dir = Path(config.output.directory)
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_basename = build_export_basename(
            timestamp=timestamp,
            article_count=len(metadata_list),
            fetch_citations=fetch_citations,
            custom_field_count=len(custom_fields or []),
        )
        output_file = output_dir / f"{export_basename}.csv"

        exporter = CSVExporter(custom_columns=custom_output_columns)
        csv_path = exporter.export(
            metadata_list,
            extraction_results,
            str(output_file),
            include_abstract=config.output.include_abstract,
            include_citations=fetch_citations,
        )

        extraction_attempted = aggregated_extraction_report.get("attempted", 0)
        extraction_success = aggregated_extraction_report.get("success", 0)
        extraction_failed = aggregated_extraction_report.get("failed", 0)
        if extraction_attempted > 0 and extraction_success == 0 and extraction_failed > 0:
            final_status = "failed"
            final_message = "Extraction failed for all LLM-eligible articles. Check API credentials or extraction errors."
        elif had_chunk_failures:
            final_status = "partial"
            final_message = "Extraction completed with some failed chunks"
        else:
            final_status = "completed"
            final_message = "Extraction completed"

        # Store only the filename, not the full path.
        persist_task(
            task_id,
            status=final_status,
            progress=1.0,
            message=final_message,
            result_file=Path(csv_path).name,
            article_report=list(article_report.values()),
            chunk_report=chunk_report,
        )

    except Exception as e:
        logger.error(f"Extraction task error: {e}")
        persist_task(task_id, status="failed", message=str(e), chunk_report=chunk_report or None)


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

    retry_task_id = f"{task_id}_retry_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    get_task_store().create_task(
        retry_task_id,
        retry_pmids,
        request_payload={
            "pmids": retry_pmids,
            "custom_fields": [field.model_dump() for field in custom_fields_payload or []],
            "fetch_citations": fetch_citations,
            "retry_of": task_id,
        },
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
