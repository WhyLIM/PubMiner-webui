# -*- coding: utf-8 -*-
"""
PubMiner API Server
FastAPI-based REST API for PubMiner functionality
"""

import os
import sys
import asyncio
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


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    result_file: Optional[str] = None
    fulltext_report: Optional[Dict[str, Any]] = None
    citation_report: Optional[Dict[str, Any]] = None
    article_report: Optional[List[Dict[str, Any]]] = None


# In-memory task storage (in production, use Redis or database)
tasks = {}
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
    )


@app.on_event("startup")
async def startup_event():
    """Initialize configuration on startup"""
    global config
    config_path = Path(__file__).parent / "config" / "default.yaml"
    config = Config.from_yaml(str(config_path))
    config.ensure_directories()
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


@app.post("/api/extract")
async def extract_information(request: ExtractionRequest, background_tasks: BackgroundTasks):
    """Extract structured information from articles"""
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Initialize task status
    tasks[task_id] = {
        "status": "pending",
        "progress": 0.0,
        "message": "Task queued",
        "result_file": None,
        "fulltext_report": None,
        "citation_report": None,
        "article_report": [],
    }

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
    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["message"] = "Fetching metadata..."
        tasks[task_id]["progress"] = 0.1

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
            tasks[task_id]["citation_report"] = {
                "enabled": True,
                "status": "running",
                "message": "Citation data is being fetched in parallel.",
                "cited_by_status": "pending",
                "references_status": "pending",
                "cited_by_total": 0,
                "references_total": 0,
            }
            citation_task = asyncio.create_task(citation_client.fetch_citation_data(pmids))
        else:
            metadata_list = await client.fetch_metadata(pmids, include_citations=False)
            tasks[task_id]["citation_report"] = {
                "enabled": False,
                "status": "disabled",
                "message": "Citation fetching was turned off for this task.",
                "cited_by_status": "disabled",
                "references_status": "disabled",
                "cited_by_total": 0,
                "references_total": 0,
            }

        article_report: Dict[str, Dict[str, Any]] = {}
        for metadata in metadata_list:
            article_report[metadata.pmid] = {
                "pmid": metadata.pmid,
                "pmcid": metadata.pmcid,
                "title": metadata.title,
                "journal": metadata.journal,
                "year": metadata.year,
                "has_fulltext": bool(metadata.pmcid),
                "fulltext_status": "pending" if metadata.pmcid else "no_pmc",
                "extraction_status": "pending" if metadata.pmcid else "skipped",
                "result_status": "pending",
                "error": "",
            }
        tasks[task_id]["article_report"] = list(article_report.values())

        tasks[task_id]["message"] = "Downloading full text..."
        tasks[task_id]["progress"] = 0.3

        # Download full text
        downloader = BioCAPIClient(
            keep_sections=config.download.sections,
            timeout=config.download.timeout,
            max_retries=config.download.max_retries,
            cache_dir=config.download.cache_dir,
        )

        # Extract PMC IDs from metadata
        pmcids = [m.pmcid for m in metadata_list if m.pmcid]
        pmids_for_download = [m.pmid for m in metadata_list if m.pmcid]

        logger.info(f"Found {len(pmcids)} articles with PMC full text out of {len(metadata_list)} total")
        tasks[task_id]["fulltext_report"] = {
            "pmc_candidates": len(pmcids),
            "downloaded": 0,
            "failed": 0,
            "fallback_used": 0,
            "cache_hits": 0,
            "cache_misses": len(pmcids),
            "failure_counts": {},
            "failure_labels": {},
            "failed_items": [],
        }

        if not pmcids:
            logger.warning("No articles with PMC full text available, skipping LLM extraction")
            fulltext_docs = []
        else:
            tasks[task_id]["message"] = f"Downloading full text for {len(pmcids)} articles..."
            fulltext_docs, fulltext_report = await downloader.batch_download_with_report(
                pmcids,
                pmids_for_download,
            )
            tasks[task_id]["fulltext_report"] = fulltext_report
            logger.info(f"Successfully downloaded {len(fulltext_docs)} full-text documents")

            for item in fulltext_report.get("items", []):
                pmid = item.get("pmid")
                if not pmid or pmid not in article_report:
                    continue
                article_report[pmid]["fulltext_status"] = item.get("reason", item.get("status", "unknown"))
                article_report[pmid]["error"] = item.get("message", "")

            for doc in fulltext_docs:
                if doc.pmid in article_report:
                    article_report[doc.pmid]["fulltext_status"] = "ready"
                    article_report[doc.pmid]["error"] = ""
            tasks[task_id]["article_report"] = list(article_report.values())

        tasks[task_id]["message"] = "Extracting information..."
        tasks[task_id]["progress"] = 0.5

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

        # Extract information
        if not fulltext_docs:
            logger.warning("No full-text documents available, skipping LLM extraction")
            extraction_results = []
            for pmid, item in article_report.items():
                if item["fulltext_status"] in {"no_pmc", "not_available"}:
                    item["extraction_status"] = "skipped"
                    item["result_status"] = "metadata_only"
                elif item["fulltext_status"] != "ready":
                    item["extraction_status"] = "skipped"
                    item["result_status"] = "metadata_only"
        else:
            tasks[task_id]["message"] = f"Extracting information from {len(fulltext_docs)} articles..."
            extractor = ZhipuExtractor(
                api_key=config.zhipu.api_key,
                model=config.zhipu.model,
                temperature=config.zhipu.temperature,
                max_retries=config.extraction.max_retries,
                use_coding_plan=config.zhipu.use_coding_plan
            )

            extraction_results = await extractor.batch_extract(
                fulltext_docs,
                schema_model,
                concurrency=config.extraction.concurrency
            )
            logger.info(f"LLM extraction completed: {len(extraction_results)} results")

            extraction_by_pmid = {result.get("pmid"): result for result in extraction_results}
            for pmid, item in article_report.items():
                if item["fulltext_status"] != "ready":
                    item["extraction_status"] = "skipped"
                    item["result_status"] = "metadata_only"
                    continue

                result = extraction_by_pmid.get(pmid)
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
            tasks[task_id]["article_report"] = list(article_report.values())

        if citation_task and citation_client:
            tasks[task_id]["message"] = "Finalizing citation data..."
            citation_data = await citation_task
            apply_citation_data(metadata_list, citation_data)
            tasks[task_id]["citation_report"] = citation_client.last_citation_report

        tasks[task_id]["message"] = "Exporting results..."
        tasks[task_id]["progress"] = 0.9

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

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 1.0
        tasks[task_id]["message"] = "Extraction completed"
        # Store only the filename, not the full path
        tasks[task_id]["result_file"] = Path(csv_path).name
        tasks[task_id]["article_report"] = list(article_report.values())

    except Exception as e:
        logger.error(f"Extraction task error: {e}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["message"] = str(e)


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get task status"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return tasks[task_id]


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
