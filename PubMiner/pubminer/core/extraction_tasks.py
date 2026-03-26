"""Shared extraction task helpers for both API and CLI entry points."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pubminer.core.config import Config
from pubminer.core.logger import get_logger
from pubminer.core.task_store import SQLiteTaskStore
from pubminer.fetcher.pubmed_client import AsyncPubMedClient
from pubminer.downloader.pmc_bioc import BioCAPIClient
from pubminer.extractor.zhipu_client import ZhipuExtractor
from pubminer.extractor.schemas.base_info import BaseExtractionModel
from pubminer.extractor.schemas.custom import CustomFieldDefinition, DynamicSchemaBuilder
from pubminer.exporter.column_mapping import COLUMN_MAPPING
from pubminer.exporter.csv_writer import CSVExporter

logger = get_logger("extraction_tasks")


def build_task_id() -> str:
    """Create a task id compatible with the web task system."""
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def stable_hash(value: str) -> str:
    """Hash a string into a stable cache key."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_schema_hash(schema_model: Any) -> str:
    """Build a stable hash for an extraction schema."""
    schema_json = schema_model.model_json_schema()
    canonical = json.dumps(schema_json, sort_keys=True, ensure_ascii=False)
    return stable_hash(canonical)


def chunk_items(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into fixed-size chunks."""
    if chunk_size <= 0:
        return [items]
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def build_export_basename(
    timestamp: str,
    article_count: int,
    fetch_citations: bool,
    custom_field_count: int,
) -> str:
    """Create a readable, stable export filename stem."""
    parts = ["pubminer", "extract", timestamp, f"{article_count}articles"]
    if fetch_citations:
        parts.append("citations")
    if custom_field_count > 0:
        parts.append(f"{custom_field_count}custom")
    return "_".join(parts)


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


def merge_fulltext_reports(accumulated: Dict[str, Any], chunk_report: Dict[str, Any]) -> Dict[str, Any]:
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
    return {"attempted": 0, "cached_hits": 0, "fresh_runs": 0, "success": 0, "failed": 0}


def merge_extraction_reports(
    accumulated: Dict[str, Any],
    *,
    attempted: int,
    cached_hits: int,
    fresh_runs: int,
    success: int,
    failed: int,
) -> Dict[str, Any]:
    merged = dict(accumulated)
    merged["attempted"] = merged.get("attempted", 0) + attempted
    merged["cached_hits"] = merged.get("cached_hits", 0) + cached_hits
    merged["fresh_runs"] = merged.get("fresh_runs", 0) + fresh_runs
    merged["success"] = merged.get("success", 0) + success
    merged["failed"] = merged.get("failed", 0) + failed
    return merged


def apply_citation_data(metadata_list: List[Any], citation_data: Dict[str, Dict[str, Any]]) -> None:
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


def persist_task(
    store: SQLiteTaskStore,
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


def create_extraction_task(
    store: SQLiteTaskStore,
    *,
    pmids: List[str],
    custom_fields: Optional[List[Any]] = None,
    fetch_citations: bool = False,
    search_session_id: Optional[str] = None,
    scope: str = "selected",
    retry_of: Optional[str] = None,
    task_id: Optional[str] = None,
) -> str:
    """Create a persisted extraction task and return its id."""
    resolved_task_id = task_id or build_task_id()
    serialized_custom_fields = []
    for field in custom_fields or []:
        if hasattr(field, "model_dump"):
            serialized_custom_fields.append(field.model_dump())
        elif isinstance(field, dict):
            serialized_custom_fields.append(field)
        else:
            serialized_custom_fields.append(vars(field))
    payload = {
        "pmids": pmids,
        "custom_fields": serialized_custom_fields,
        "fetch_citations": fetch_citations,
        "search_session_id": search_session_id,
        "scope": scope,
    }
    if retry_of:
        payload["retry_of"] = retry_of
    store.create_task(resolved_task_id, pmids, request_payload=payload)
    return resolved_task_id


async def run_extraction_task(
    *,
    config: Config,
    store: SQLiteTaskStore,
    task_id: str,
    pmids: List[str],
    custom_fields: Optional[List[Any]],
    fetch_citations: bool = False,
) -> None:
    """Run the extraction task using the persisted web task format."""
    chunk_report: List[Dict[str, Any]] = []
    try:
        persist_task(store, task_id, status="running", message="Fetching metadata...", progress=0.1)

        client = AsyncPubMedClient(
            email=config.ncbi.email,
            api_key=config.ncbi.api_key,
            tool_name=config.ncbi.tool_name,
            rate_limit=config.ncbi.rate_limit,
        )

        citation_task = None
        citation_client = None

        if fetch_citations:
            metadata_list = await client.fetch_metadata(pmids, include_citations=False)
            citation_client = AsyncPubMedClient(
                email=config.ncbi.email,
                api_key=config.ncbi.api_key,
                tool_name=config.ncbi.tool_name,
                rate_limit=config.ncbi.rate_limit,
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
            persist_task(store, task_id, citation_report=citation_report)
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
            persist_task(store, task_id, citation_report=citation_report)

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
        persist_task(store, task_id, article_report=list(article_report.values()))

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
        persist_task(store, task_id, chunk_report=chunk_report)

        schema_model = BaseExtractionModel
        custom_output_columns: List[str] = []
        if custom_fields:
            custom_definitions = []
            for field in custom_fields:
                field_type = "str"
                if getattr(field, "type", None) == "number":
                    field_type = "float"
                elif getattr(field, "type", None) == "enum":
                    field_type = "enum"
                custom_definitions.append(
                    CustomFieldDefinition(
                        name=field.name,
                        description=field.description,
                        field_type=field_type,
                        enum_values=getattr(field, "enumValues", None) or [],
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
            use_coding_plan=config.zhipu.use_coding_plan,
        )
        extraction_schema_hash = build_schema_hash(schema_model)
        had_chunk_failures = False

        for chunk_index, metadata_chunk in enumerate(metadata_chunks, start=1):
            chunk_message = f"Processing chunk {chunk_index}/{total_chunks} ({len(metadata_chunk)} articles)"
            chunk_entry = chunk_report[chunk_index - 1]
            chunk_entry["status"] = "running"
            chunk_entry["message"] = chunk_message
            persist_task(
                store,
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
                    chunk_fulltext_docs, chunk_fulltext_report = await downloader.batch_download_with_report(pmcids, pmids_for_download)
                    aggregated_fulltext_report = merge_fulltext_reports(aggregated_fulltext_report, chunk_fulltext_report)
                else:
                    chunk_fulltext_report = create_empty_fulltext_report()

                chunk_entry["fulltext_downloaded"] = len(chunk_fulltext_docs)
                persist_task(store, task_id, fulltext_report=aggregated_fulltext_report)

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
                        cached_result = store.get_extraction_cache(
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
                            concurrency=config.extraction.concurrency,
                        )
                        for result in fresh_results:
                            if "error" not in result and result.get("pmid"):
                                matching_doc = docs_by_pmid.get(result.get("pmid"))
                                if matching_doc is not None:
                                    store.put_extraction_cache(
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
                    persist_task(store, task_id, extraction_report=aggregated_extraction_report)
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
                logger.error("Chunk %s failed in task %s: %s", chunk_index, task_id, chunk_error)
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
                store,
                task_id,
                article_report=list(article_report.values()),
                extraction_report=aggregated_extraction_report,
                progress=0.1 + (0.7 * (chunk_index / total_chunks)),
                chunk_report=chunk_report,
            )

        if citation_task and citation_client:
            persist_task(store, task_id, message="Finalizing citation data...")
            citation_data = await citation_task
            apply_citation_data(metadata_list, citation_data)
            for item in article_report.values():
                item["citation_status"] = "success"
            persist_task(store, task_id, citation_report=citation_client.last_citation_report)
            persist_task(store, task_id, article_report=list(article_report.values()))

        persist_task(store, task_id, message="Exporting results...", progress=0.9)
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

        persist_task(
            store,
            task_id,
            status=final_status,
            progress=1.0,
            message=final_message,
            result_file=Path(csv_path).name,
            article_report=list(article_report.values()),
            chunk_report=chunk_report,
        )
    except Exception as exc:
        logger.error("Extraction task error: %s", exc)
        persist_task(store, task_id, status="failed", message=str(exc), chunk_report=chunk_report or None)
        raise
