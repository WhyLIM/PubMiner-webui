"""
Main CLI entry point for PubMiner.

Provides command-line interface for running the literature mining pipeline.
"""

import asyncio
import argparse
import sys
import json
import hashlib
import zipfile
import tempfile
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable

import aiohttp
import yaml
from rich.console import Console
from rich.progress import Progress, TextColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from pubminer.core.config import Config
from pubminer.core.state import StateManager, ProcessingStage
from pubminer.core.logger import setup_logger, get_logger
from pubminer.core.exceptions import PubMinerError
from pubminer.core.task_store import SQLiteTaskStore
from pubminer.core.extraction_tasks import (
    build_task_id as build_persisted_task_id,
    create_extraction_task as create_persisted_extraction_task,
    run_extraction_task as run_persisted_extraction_task,
)
from pubminer.fetcher.pubmed_client import AsyncPubMedClient
from pubminer.downloader.pmc_bioc import BioCAPIClient
from pubminer.downloader.oa_pdf import OAPdfResolver
from pubminer.downloader.section_parser import SectionType
from pubminer.extractor.zhipu_client import ZhipuExtractor
from pubminer.extractor.schemas.base_info import BaseExtractionModel
from pubminer.extractor.schemas.custom import DynamicSchemaBuilder
from pubminer.exporter.csv_writer import CSVExporter

console = Console()
logger = None  # Will be initialized in main()


def make_progress() -> Progress:
    """Return a Windows-safe progress renderer without Unicode spinners/bars."""
    return Progress(TextColumn("[progress.description]{task.description}"), console=console)


def stable_hash(value: str) -> str:
    """Return a stable hash for identifiers and session ids."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_search_session_id(query: str, max_results: int) -> str:
    """Create a local search session id."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"search_{timestamp}_{stable_hash(f'{query}|{max_results}|{timestamp}')[:10]}"


def load_config(config_path: str, *, output_override: Optional[str] = None, max_results: Optional[int] = None) -> Config:
    """Load config and apply simple CLI overrides."""
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]Error: Configuration file not found: {config_path}[/red]")
        sys.exit(1)

    config = Config.from_yaml(str(config_file))
    if output_override:
        config.output.directory = output_override
    if max_results is not None:
        config.search.max_results = max_results
    config.ensure_directories()
    return config


def validate_config(config: Config, *, require_zhipu: bool = False) -> None:
    """Validate the minimum runtime configuration needed for a command."""
    if not config.ncbi.email or config.ncbi.email == "your_email@example.com":
        console.print("[red]Error: NCBI email is required. Please set it in config.yaml[/red]")
        sys.exit(1)
    if require_zhipu and (not config.zhipu.api_key or config.zhipu.api_key == "${ZHIPU_API_KEY}"):
        console.print("[red]Error: Zhipu API key is required. Set ZHIPU_API_KEY or update config.yaml[/red]")
        sys.exit(1)


def get_task_store(config: Config) -> SQLiteTaskStore:
    """Open the local SQLite task store."""
    return SQLiteTaskStore(config.database.path)


def read_pmids_file(path: str) -> List[str]:
    """Read PMIDs from a text file."""
    with open(path, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip().isdigit()]


def metadata_to_article_payload(meta: Any) -> Dict[str, Any]:
    """Convert metadata model into the OA article request shape."""
    return {
        "pmid": getattr(meta, "pmid", ""),
        "doi": getattr(meta, "doi", None),
        "pmcid": getattr(meta, "pmcid", None),
        "title": getattr(meta, "title", None),
    }


def metadata_to_search_row(meta: Any) -> Dict[str, str]:
    """Convert metadata into a simple CLI table row."""
    return {
        "pmid": str(getattr(meta, "pmid", "") or ""),
        "year": str(getattr(meta, "year", "") or ""),
        "pmcid": str(getattr(meta, "pmcid", "") or ""),
        "journal": str(getattr(meta, "journal", "") or ""),
        "title": str(getattr(meta, "title", "") or ""),
    }


def load_custom_fields_payload(path: str) -> List[Any]:
    """Load custom field entries from YAML into attribute-style objects."""
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [SimpleNamespace(**field) for field in payload.get("fields", [])]


def build_oa_pdf_resolver(config: Config, *, unpaywall_email: Optional[str] = None, fast_pmc_only: bool = False) -> OAPdfResolver:
    """Create an OA PDF resolver that mirrors the backend defaults."""
    effective_email = unpaywall_email or config.oa_pdf.unpaywall_email
    if effective_email and "${" in effective_email:
        effective_email = None

    if fast_pmc_only:
        return OAPdfResolver(
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

    return OAPdfResolver(
        timeout=config.oa_pdf.fallback_timeout,
        max_retries=config.oa_pdf.fallback_max_retries,
        prefer_pmc=config.oa_pdf.prefer_pmc,
        strict_oa=config.oa_pdf.strict_oa,
        cache_dir=config.oa_pdf.cache_dir,
        cache_only_when_license_known=config.oa_pdf.cache_only_when_license_known,
        unpaywall_email=effective_email,
        enable_pmc=config.oa_pdf.enable_pmc,
        enable_unpaywall=config.oa_pdf.enable_unpaywall,
        enable_europepmc=config.oa_pdf.enable_europepmc,
        resolve_concurrency=config.oa_pdf.resolve_concurrency,
    )


async def resolve_input_pmids(
    config: Config,
    store: SQLiteTaskStore,
    *,
    query: Optional[str] = None,
    pmid_file: Optional[str] = None,
    session_id: Optional[str] = None,
    pmids_inline: Optional[List[str]] = None,
    max_results: Optional[int] = None,
) -> List[str]:
    """Resolve PMIDs from query, file, session, or inline values."""
    if session_id:
        session = store.get_search_session(session_id)
        if session is None:
            raise PubMinerError(f"Search session not found: {session_id}")
        return list(session.get("pmids", []))

    if pmid_file:
        return read_pmids_file(pmid_file)

    if pmids_inline:
        return [pmid.strip() for pmid in pmids_inline if str(pmid).strip()]

    if query:
        client = AsyncPubMedClient(email=config.ncbi.email, api_key=config.ncbi.api_key)
        effective_max = max_results or config.search.max_results
        search_result = await client.search(query, max_results=effective_max, offset=0)
        pmids = search_result["pmids"]
        session_id = build_search_session_id(query, effective_max)
        store.save_search_session(
            session_id=session_id,
            source="cli",
            query=query,
            total_available=search_result["total_count"],
            scope_limit=effective_max,
            pmids=pmids,
        )
        console.print(f"[dim]Saved search session:[/dim] {session_id}")
        return pmids

    raise PubMinerError("Provide one of: --query, --file, --session-id, or --pmids")


async def run_pipeline(
    config: Config,
    query: Optional[str] = None,
    pmid_file: Optional[str] = None,
    pmids: Optional[List[str]] = None,
    search_session_id: Optional[str] = None,
    custom_fields_file: Optional[str] = None,
    resume: bool = False,
) -> str:
    """
    Run the complete PubMiner pipeline.

    Args:
        config: Configuration object
        query: PubMed search query
        pmid_file: Path to file containing PMIDs
        custom_fields_file: Path to custom fields YAML
        resume: Whether to resume from checkpoint

    Returns:
        Path to output CSV file
    """
    global logger
    logger = get_logger("pipeline")

    # Initialize state manager
    state = StateManager(config.checkpoint.directory)

    # Check for resume
    if resume and state.has_previous_run():
        run_info = state.get_run_info()
        console.print(Panel(
            f"[yellow]Resuming previous run[/yellow]\n"
            f"Query: {run_info['query'] or run_info['pmid_file']}\n"
            f"Last updated: {run_info['last_updated']}",
            title="Checkpoint Found",
        ))
        pmids = state.get_all_pmids()
    else:
        # Initialize clients
        pubmed_client = AsyncPubMedClient(
            email=config.ncbi.email,
            api_key=config.ncbi.api_key,
        )

        # Step 1: Get PMIDs
        if pmids:
            console.print(f"[cyan]Using {len(pmids)} PMIDs provided by CLI[/cyan]")
        elif search_session_id:
            store = get_task_store(config)
            session = store.get_search_session(search_session_id)
            if session is None:
                raise PubMinerError(f"Search session not found: {search_session_id}")
            pmids = list(session.get("pmids", []))
            console.print(f"[cyan]Using search session:[/cyan] {search_session_id} ({len(pmids)} PMIDs)")
        elif pmid_file:
            console.print(f"[cyan]Loading PMIDs from file:[/cyan] {pmid_file}")
            pmids = read_pmids_file(pmid_file)
        else:
            with make_progress() as progress:
                task = progress.add_task("Searching PubMed...", total=None)
                search_result = await pubmed_client.search(
                    query,
                    max_results=config.search.max_results,
                )
                pmids = search_result["pmids"] if isinstance(search_result, dict) else search_result

        console.print(f"[green]Found {len(pmids)} articles to process[/green]")

        # Initialize state
        state.initialize_run(
            query=query,
            pmid_file=pmid_file,
            pmids=pmids,
        )

    # Step 2: Fetch metadata
    console.print("\n[bold]Step 1: Fetching metadata[/bold]")

    pubmed_client = AsyncPubMedClient(
        email=config.ncbi.email,
        api_key=config.ncbi.api_key,
    )

    with make_progress() as progress:
        task = progress.add_task("Fetching metadata...", total=len(pmids))
        metadata_list = await pubmed_client.fetch_metadata(pmids)
        progress.update(task, completed=len(pmids))

    # Update state for fetched
    for meta in metadata_list:
        state.update_pmid(
            meta.pmid,
            ProcessingStage.FETCHED,
            has_fulltext=meta.has_pmc_fulltext,
            pmcid=meta.pmcid,
        )

    console.print(f"[green]✓ Fetched metadata for {len(metadata_list)} articles[/green]")

    # Count articles with full text
    has_fulltext = sum(1 for m in metadata_list if m.has_pmc_fulltext)
    console.print(f"[dim]  {has_fulltext} have PMC full text available[/dim]")

    # Step 3: Download full text
    console.print("\n[bold]Step 2: Downloading full text[/bold]")

    bioc_client = BioCAPIClient(
        timeout=config.download.timeout,
        max_retries=config.download.max_retries,
        keep_sections=[SectionType[s] for s in config.download.sections if s in SectionType.__members__],
    )

    # Prepare documents for extraction
    documents = []

    async with aiohttp.ClientSession() as session:
        with make_progress() as progress:
            task = progress.add_task("Downloading full text...", total=len(metadata_list))

            for meta in metadata_list:
                if meta.pmcid:
                    doc = await bioc_client.get_filtered_document(
                        session,
                        meta.pmcid,
                        meta.pmid,
                    )

                    if doc:
                        documents.append({
                            "pmid": meta.pmid,
                            "text": doc.filtered_text,
                            "title": meta.title,
                        })
                        state.update_pmid(meta.pmid, ProcessingStage.DOWNLOADED)

                progress.update(task, advance=1)

    console.print(f"[green]✓ Downloaded {len(documents)} full-text articles[/green]")

    if not documents:
        console.print("[red]No full-text articles available for extraction![/red]")
        console.print("[yellow]Tip: Try a different search query or check PMC availability.[/yellow]")
        return ""

    # Step 4: LLM Extraction
    console.print("\n[bold]Step 3: Extracting structured information[/bold]")

    # Build schema
    if custom_fields_file:
        console.print(f"[dim]Loading custom fields from: {custom_fields_file}[/dim]")
        schema_model = DynamicSchemaBuilder.from_yaml(custom_fields_file)
    else:
        schema_model = BaseExtractionModel

    extractor = ZhipuExtractor(
        api_key=config.zhipu.api_key,
        model=config.zhipu.model,
        temperature=config.zhipu.temperature,
        max_tokens=config.zhipu.max_tokens,
        max_retries=config.extraction.max_retries,
        rate_limit=config.zhipu.rate_limit,
    )

    with make_progress() as progress:
        task = progress.add_task("Extracting with LLM...", total=len(documents))

        extraction_results = await extractor.batch_extract(
            documents,
            schema_model,
            concurrency=config.extraction.concurrency,
        )

        # Update state
        for result in extraction_results:
            pmid = result.get("pmid", "")
            if "error" not in result:
                state.update_pmid(pmid, ProcessingStage.EXTRACTED)
            else:
                state.update_pmid(pmid, ProcessingStage.FAILED, error=result.get("error"))
            progress.update(task, advance=1)

    # Count successes
    success_count = sum(1 for r in extraction_results if "error" not in r)
    console.print(f"[green]✓ Successfully extracted {success_count}/{len(documents)} articles[/green]")

    # Step 5: Export results
    console.print("\n[bold]Step 4: Exporting results[/bold]")

    exporter = CSVExporter()

    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{config.output.filename_prefix}_{timestamp}.csv"
    output_path = Path(config.output.directory) / output_filename

    csv_path = exporter.export(
        metadata_list,
        extraction_results,
        str(output_path),
        include_abstract=config.output.include_abstract,
    )

    # Update final state
    for result in extraction_results:
        if "error" not in result:
            state.update_pmid(result.get("pmid", ""), ProcessingStage.COMPLETED)

    # Show summary
    progress_info = state.get_progress()

    summary_table = Table(title="Processing Summary", show_header=False)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total articles", str(progress_info["total"]))
    summary_table.add_row("Full-text downloaded", str(len(documents)))
    summary_table.add_row("Successfully extracted", str(success_count))
    summary_table.add_row("Failed", str(progress_info["failed"]))
    summary_table.add_row("Output file", csv_path)

    console.print()
    console.print(summary_table)

    return csv_path


async def run_extract_command(config: Config, args: argparse.Namespace) -> int:
    """Run extraction using the same persisted task/chunk flow as the web app."""
    validate_config(config, require_zhipu=True)
    store = get_task_store(config)
    pmids = await resolve_input_pmids(
        config,
        store,
        query=args.query,
        pmid_file=args.file,
        session_id=args.session_id,
        pmids_inline=args.pmids,
        max_results=args.max_results,
    )
    if not pmids:
        raise PubMinerError("No PMIDs were resolved for extraction")

    custom_fields_payload = []
    if args.custom_fields:
        custom_fields_payload = load_custom_fields_payload(args.custom_fields)

    task_id = create_persisted_extraction_task(
        store,
        pmids=pmids,
        custom_fields=custom_fields_payload,
        fetch_citations=False,
        search_session_id=args.session_id,
        scope="all_matched" if args.session_id else "selected",
        task_id=build_persisted_task_id(),
    )

    console.print(Panel.fit(
        f"[bold]Extraction task started[/bold]\n"
        f"task_id: {task_id}\n"
        f"articles: {len(pmids)}",
        border_style="blue",
    ))

    await run_persisted_extraction_task(
        config=config,
        store=store,
        task_id=task_id,
        pmids=pmids,
        custom_fields=custom_fields_payload,
        fetch_citations=False,
    )
    task = store.get_task(task_id)
    if task:
        console.print(
            f"[green]Task finished:[/green] {task_id} "
            f"status={task.get('status')} result={task.get('result_file') or '-'}"
        )
    return 0


async def run_search_command(config: Config, args: argparse.Namespace) -> int:
    """Search PubMed, persist a search session, and preview the first page."""
    validate_config(config)
    store = get_task_store(config)
    client = AsyncPubMedClient(email=config.ncbi.email, api_key=config.ncbi.api_key)
    effective_max = args.max_results or config.search.max_results
    preview_size = max(1, min(args.load_size, 100, effective_max))

    with make_progress() as progress:
        task = progress.add_task("Searching PubMed...", total=None)
        search_result = await client.search(args.query, max_results=effective_max, offset=0)
        session_id = build_search_session_id(args.query, effective_max)
        store.save_search_session(
            session_id=session_id,
            source="cli",
            query=args.query,
            total_available=search_result["total_count"],
            scope_limit=effective_max,
            pmids=search_result["pmids"],
        )
        preview_pmids = search_result["pmids"][:preview_size]
        metadata_list = await client.fetch_metadata(preview_pmids, include_citations=False)
        progress.update(task, completed=1)

    console.print(Panel.fit(
        f"[bold]Search session[/bold]\n"
        f"session_id: {session_id}\n"
        f"total_available: {search_result['total_count']}\n"
        f"session_total: {len(search_result['pmids'])}\n"
        f"loaded_preview: {len(metadata_list)}",
        border_style="blue",
    ))

    table = Table(title="Loaded Preview")
    table.add_column("PMID", style="cyan", no_wrap=True)
    table.add_column("Year", style="green", no_wrap=True)
    table.add_column("PMCID", style="magenta", no_wrap=True)
    table.add_column("Journal", style="yellow")
    table.add_column("Title", style="white")
    for meta in metadata_list:
        row = metadata_to_search_row(meta)
        table.add_row(row["pmid"], row["year"], row["pmcid"], row["journal"], row["title"])
    console.print(table)

    if args.json_out:
        payload = {
            "session_id": session_id,
            "query": args.query,
            "total_available": search_result["total_count"],
            "session_total": len(search_result["pmids"]),
            "loaded_preview": [metadata_to_article_payload(meta) | {"year": getattr(meta, "year", None)} for meta in metadata_list],
        }
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]Saved JSON preview:[/green] {args.json_out}")
    return 0


async def run_oa_check_command(config: Config, args: argparse.Namespace) -> int:
    """Resolve OA PDF availability for a PMID set."""
    validate_config(config)
    store = get_task_store(config)
    pmids = await resolve_input_pmids(
        config,
        store,
        query=args.query,
        pmid_file=args.file,
        session_id=args.session_id,
        pmids_inline=args.pmids,
        max_results=args.max_results,
    )
    if args.limit:
        pmids = pmids[:args.limit]
    if not pmids:
        raise PubMinerError("No PMIDs were resolved for OA checking")

    client = AsyncPubMedClient(email=config.ncbi.email, api_key=config.ncbi.api_key)
    metadata_list = await client.fetch_metadata(pmids, include_citations=False)
    resolver = build_oa_pdf_resolver(config, unpaywall_email=args.unpaywall_email)
    resolutions = await resolver.resolve_many([metadata_to_article_payload(meta) for meta in metadata_list])

    table = Table(title="OA PDF Check")
    table.add_column("PMID", style="cyan", no_wrap=True)
    table.add_column("PMCID", style="magenta", no_wrap=True)
    table.add_column("Availability", style="green", no_wrap=True)
    table.add_column("Source", style="yellow", no_wrap=True)
    table.add_column("Reason", style="white")

    available_count = 0
    for resolution in resolutions:
        source = resolution.best_candidate.source if resolution.best_candidate else "-"
        if resolution.availability == "available":
            available_count += 1
        table.add_row(
            resolution.pmid,
            resolution.pmcid or "",
            resolution.availability,
            source,
            resolution.reason,
        )
    console.print(table)
    console.print(f"[bold green]Available:[/bold green] {available_count}/{len(resolutions)}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps([item.model_dump() for item in resolutions], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"[green]Saved OA check JSON:[/green] {args.json_out}")
    return 0


async def run_oa_download_command(config: Config, args: argparse.Namespace) -> int:
    """Download OA PDFs for a PMID set and optionally package them into a zip."""
    validate_config(config)
    store = get_task_store(config)
    pmids = await resolve_input_pmids(
        config,
        store,
        query=args.query,
        pmid_file=args.file,
        session_id=args.session_id,
        pmids_inline=args.pmids,
        max_results=args.max_results,
    )
    if args.limit:
        pmids = pmids[:args.limit]
    if not pmids:
        raise PubMinerError("No PMIDs were resolved for OA download")

    client = AsyncPubMedClient(email=config.ncbi.email, api_key=config.ncbi.api_key)
    metadata_list = await client.fetch_metadata(pmids, include_citations=False)
    articles = [metadata_to_article_payload(meta) for meta in metadata_list]

    pmc_first_articles = [article for article in articles if article.get("pmcid")]
    fallback_only_articles = [article for article in articles if not article.get("pmcid")]
    records_by_pmid: Dict[str, Any] = {}

    if pmc_first_articles:
        fast_resolver = build_oa_pdf_resolver(config, fast_pmc_only=True)
        fast_records = await fast_resolver.download_many(
            pmc_first_articles,
            concurrency=config.oa_pdf.pmc_download_concurrency,
        )
        for record in fast_records:
            records_by_pmid[record.pmid] = record
        retry_articles = [
            article for article in pmc_first_articles
            if records_by_pmid.get(article.get("pmid")) is not None
            and records_by_pmid[article.get("pmid")].status != "downloaded"
        ]
    else:
        retry_articles = []

    retry_articles.extend(fallback_only_articles)

    if retry_articles:
        fallback_resolver = build_oa_pdf_resolver(config, unpaywall_email=args.unpaywall_email)
        fallback_records = await fallback_resolver.download_many(
            retry_articles,
            concurrency=config.oa_pdf.fallback_download_concurrency,
        )
        for record in fallback_records:
            records_by_pmid[record.pmid] = record

    records = [records_by_pmid[article["pmid"]] for article in articles if article.get("pmid") in records_by_pmid]
    successful_records = [record for record in records if record.status == "downloaded" and record.local_path]

    summary = Table(title="OA PDF Download Summary")
    summary.add_column("PMID", style="cyan", no_wrap=True)
    summary.add_column("Status", style="green", no_wrap=True)
    summary.add_column("Source", style="yellow", no_wrap=True)
    summary.add_column("Elapsed (ms)", style="magenta", no_wrap=True)
    summary.add_column("File", style="white")
    for record in records:
        summary.add_row(
            record.pmid,
            record.status,
            record.source,
            str(record.elapsed_ms or ""),
            record.filename or record.error or "",
        )
    console.print(summary)
    console.print(f"[bold green]Downloaded:[/bold green] {len(successful_records)}/{len(records)}")

    if args.manifest_out:
        Path(args.manifest_out).write_text(
            json.dumps([record.model_dump() for record in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"[green]Saved manifest:[/green] {args.manifest_out}")

    if args.zip_output:
        with zipfile.ZipFile(args.zip_output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for record in successful_records:
                file_path = Path(record.local_path)
                if file_path.exists():
                    archive.write(file_path, arcname=record.filename or file_path.name)
            archive.writestr(
                "manifest.json",
                json.dumps([record.model_dump() for record in records], ensure_ascii=False, indent=2),
            )
        console.print(f"[green]Saved zip:[/green] {args.zip_output}")
    return 0


def run_tasks_command(config: Config, args: argparse.Namespace) -> int:
    """Inspect persisted tasks and search sessions."""
    store = get_task_store(config)

    if args.view == "sessions":
        sessions = store.list_search_sessions(limit=args.limit)
        table = Table(title="Search Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Scope", style="green", no_wrap=True)
        table.add_column("Available", style="yellow", no_wrap=True)
        table.add_column("Updated", style="magenta", no_wrap=True)
        table.add_column("Query", style="white")
        for session in sessions:
            table.add_row(
                session["session_id"],
                str(session["scope_limit"]),
                str(session["total_available"]),
                session["updated_at"],
                session["query"],
            )
        console.print(table)
        return 0

    if args.task_id:
        task = store.get_task(args.task_id)
        if task is None:
            raise PubMinerError(f"Task not found: {args.task_id}")
        console.print_json(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    tasks = store.list_tasks(limit=args.limit)
    table = Table(title="Tasks")
    table.add_column("Task ID", style="cyan")
    table.add_column("Status", style="green", no_wrap=True)
    table.add_column("Progress", style="yellow", no_wrap=True)
    table.add_column("Updated", style="magenta", no_wrap=True)
    table.add_column("Message", style="white")
    for task in tasks:
        table.add_row(
            task["task_id"],
            task["status"],
            f"{task['progress']:.0%}",
            task["updated_at"],
            task["message"],
        )
    console.print(table)
    return 0


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="pubminer",
        description="PubMiner: Intelligent Medical Literature Mining Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search PubMed and extract
  pubminer -q "aging biomarkers AND humans" -c config/default.yaml

  # Use PMID list
  pubminer -f pmids.txt -c config/default.yaml

  # With custom fields
  pubminer -q "senescence markers" --custom-fields config/custom_fields.yaml

  # Resume interrupted run
  pubminer --resume
        """,
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-q", "--query",
        help="PubMed search query"
    )
    input_group.add_argument(
        "-f", "--file",
        help="Path to file containing PMIDs (one per line)"
    )
    input_group.add_argument(
        "--resume",
        action="store_true",
        help="Resume interrupted processing"
    )

    # Configuration options
    parser.add_argument(
        "-c", "--config",
        default="config/default.yaml",
        help="Path to configuration file (default: config/default.yaml)"
    )
    parser.add_argument(
        "--custom-fields",
        help="Path to custom fields YAML file"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (overrides config)"
    )
    parser.add_argument(
        "--max-results",
        type=int,
        help="Maximum number of results (overrides config)"
    )

    # Logging options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--log-file",
        help="Path to log file"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger(level=log_level, log_file=args.log_file)

    global logger
    logger = get_logger("main")

    try:
        # Load configuration
        config_path = Path(args.config)
        if not config_path.exists():
            console.print(f"[red]Error: Configuration file not found: {args.config}[/red]")
            console.print("[yellow]Please create a config file or use -c to specify a path.[/yellow]")
            sys.exit(1)

        config = Config.from_yaml(str(config_path))

        # Override config with CLI args
        if args.output:
            config.output.directory = args.output
        if args.max_results:
            config.search.max_results = args.max_results

        # Ensure directories exist
        config.ensure_directories()

        # Validate required configuration
        if not config.ncbi.email or config.ncbi.email == "your_email@example.com":
            console.print("[red]Error: NCBI email is required. Please set it in config.yaml[/red]")
            sys.exit(1)

        if not config.zhipu.api_key or config.zhipu.api_key == "${ZHIPU_API_KEY}":
            console.print("[red]Error: Zhipu API key is required. Set ZHIPU_API_KEY environment variable or update config.yaml[/red]")
            sys.exit(1)

        # Show banner
        console.print(Panel.fit(
            "[bold blue]PubMiner[/bold blue] - Medical Literature Mining Tool\n"
            "[dim]Version 0.1.0[/dim]",
            border_style="blue",
        ))

        # Run pipeline
        output_path = asyncio.run(
            run_pipeline(
                config=config,
                query=args.query,
                pmid_file=args.file,
                custom_fields_file=args.custom_fields,
                resume=args.resume,
            )
        )

        if output_path:
            console.print(f"\n[green]✓ Done! Results saved to:[/green] {output_path}")
        else:
            console.print("\n[yellow]Pipeline completed with warnings.[/yellow]")
            sys.exit(0)

    except PubMinerError as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user. Use --resume to continue later.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        logger.exception("Unexpected error")
        sys.exit(1)

def build_input_source_group(parser: argparse.ArgumentParser, *, require: bool = False):
    """Create a reusable CLI input-source group."""
    group = parser.add_mutually_exclusive_group(required=require)
    group.add_argument("-q", "--query", help="PubMed search query")
    group.add_argument("-f", "--file", help="Path to file containing PMIDs (one per line)")
    group.add_argument("--session-id", help="Existing backend search session id")
    group.add_argument("--pmids", nargs="+", help="One or more PMIDs provided inline")
    return group


def legacy_main(argv: Optional[List[str]] = None) -> int:
    """Backward-compatible legacy pipeline entry point."""
    parser = argparse.ArgumentParser(
        prog="pubminer",
        description="PubMiner: Intelligent Medical Literature Mining Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search PubMed and extract
  pubminer -q "aging biomarkers AND humans" -c config/default.yaml

  # Use PMID list
  pubminer -f pmids.txt -c config/default.yaml

  # With custom fields
  pubminer -q "senescence markers" --custom-fields config/custom_fields.yaml

  # Resume interrupted run
  pubminer --resume
        """,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-q", "--query", help="PubMed search query")
    input_group.add_argument("-f", "--file", help="Path to file containing PMIDs (one per line)")
    input_group.add_argument("--resume", action="store_true", help="Resume interrupted processing")
    parser.add_argument("-c", "--config", default="config/default.yaml", help="Path to configuration file")
    parser.add_argument("--custom-fields", help="Path to custom fields YAML file")
    parser.add_argument("-o", "--output", help="Output directory (overrides config)")
    parser.add_argument("--max-results", type=int, help="Maximum number of results (overrides config)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--log-file", help="Path to log file")

    args = parser.parse_args(argv)
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger(level=log_level, log_file=args.log_file)

    global logger
    logger = get_logger("main")

    try:
        config = load_config(args.config, output_override=args.output, max_results=args.max_results)
        validate_config(config, require_zhipu=True)

        console.print(Panel.fit(
            "[bold blue]PubMiner[/bold blue] - Medical Literature Mining Tool\n"
            "[dim]Version 0.1.0[/dim]",
            border_style="blue",
        ))

        output_path = asyncio.run(
            run_pipeline(
                config=config,
                query=args.query,
                pmid_file=args.file,
                custom_fields_file=args.custom_fields,
                resume=args.resume,
            )
        )

        if output_path:
            console.print(f"\n[green]Done! Results saved to:[/green] {output_path}")
        else:
            console.print("\n[yellow]Pipeline completed with warnings.[/yellow]")
            return 0
    except PubMinerError as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.error(f"Pipeline failed: {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user. Use --resume to continue later.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        logger.exception("Unexpected error")
        return 1
    return 0


def subcommand_main(argv: Optional[List[str]] = None) -> int:
    """Subcommand-based CLI entry point."""
    parser = argparse.ArgumentParser(prog="pubminer", description="PubMiner command-line interface")
    parser.add_argument("-c", "--config", default="config/default.yaml", help="Path to configuration file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--log-file", help="Path to log file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search PubMed and save a search session")
    search_parser.add_argument("-q", "--query", required=True, help="PubMed search query")
    search_parser.add_argument("--max-results", type=int, help="Maximum matched records to keep in the search session")
    search_parser.add_argument("--load-size", type=int, default=20, help="How many metadata rows to preview immediately")
    search_parser.add_argument("--json-out", help="Optional path to write the preview payload as JSON")

    oa_check_parser = subparsers.add_parser("oa-check", help="Resolve legal OA PDF availability")
    build_input_source_group(oa_check_parser, require=True)
    oa_check_parser.add_argument("--max-results", type=int, help="Maximum search results when using --query")
    oa_check_parser.add_argument("--limit", type=int, help="Only check the first N resolved PMIDs")
    oa_check_parser.add_argument("--unpaywall-email", help="Email to use for Unpaywall lookups")
    oa_check_parser.add_argument("--json-out", help="Optional path to write OA check results as JSON")

    oa_download_parser = subparsers.add_parser("oa-download", help="Download legal OA PDFs")
    build_input_source_group(oa_download_parser, require=True)
    oa_download_parser.add_argument("--max-results", type=int, help="Maximum search results when using --query")
    oa_download_parser.add_argument("--limit", type=int, help="Only download the first N resolved PMIDs")
    oa_download_parser.add_argument("--unpaywall-email", help="Email to use for Unpaywall lookups")
    oa_download_parser.add_argument("--manifest-out", help="Optional path to write the download manifest JSON")
    oa_download_parser.add_argument("--zip-output", help="Optional path to package all successful PDFs into a zip")

    extract_parser = subparsers.add_parser("extract", help="Run the extraction pipeline from query, PMIDs, or a search session")
    build_input_source_group(extract_parser, require=True)
    extract_parser.add_argument("--max-results", type=int, help="Maximum search results when using --query")
    extract_parser.add_argument("--custom-fields", help="Path to custom fields YAML file")
    extract_parser.add_argument("-o", "--output", help="Output directory (overrides config)")

    tasks_parser = subparsers.add_parser("tasks", help="Inspect persisted tasks or search sessions")
    tasks_parser.add_argument("--task-id", help="Show a specific task as JSON")
    tasks_parser.add_argument("--view", choices=["tasks", "sessions"], default="tasks", help="Which persisted object type to list")
    tasks_parser.add_argument("--limit", type=int, default=20, help="Maximum number of rows to show")

    pipeline_parser = subparsers.add_parser("pipeline", help="Run the legacy all-in-one pipeline")
    input_group = pipeline_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-q", "--query", help="PubMed search query")
    input_group.add_argument("-f", "--file", help="Path to file containing PMIDs (one per line)")
    input_group.add_argument("--resume", action="store_true", help="Resume interrupted processing")
    pipeline_parser.add_argument("--custom-fields", help="Path to custom fields YAML file")
    pipeline_parser.add_argument("-o", "--output", help="Output directory (overrides config)")
    pipeline_parser.add_argument("--max-results", type=int, help="Maximum number of results (overrides config)")

    args = parser.parse_args(argv)
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger(level=log_level, log_file=args.log_file)

    global logger
    logger = get_logger("main")

    try:
        config = load_config(
            args.config,
            output_override=getattr(args, "output", None),
            max_results=getattr(args, "max_results", None),
        )

        if args.command == "search":
            return asyncio.run(run_search_command(config, args))
        if args.command == "oa-check":
            return asyncio.run(run_oa_check_command(config, args))
        if args.command == "oa-download":
            return asyncio.run(run_oa_download_command(config, args))
        if args.command == "extract":
            return asyncio.run(run_extract_command(config, args))
        if args.command == "tasks":
            return run_tasks_command(config, args)
        if args.command == "pipeline":
            legacy_args: List[str] = []
            if args.query:
                legacy_args.extend(["-q", args.query])
            if args.file:
                legacy_args.extend(["-f", args.file])
            if args.resume:
                legacy_args.append("--resume")
            if args.custom_fields:
                legacy_args.extend(["--custom-fields", args.custom_fields])
            if args.output:
                legacy_args.extend(["-o", args.output])
            if args.max_results:
                legacy_args.extend(["--max-results", str(args.max_results)])
            legacy_args.extend(["-c", args.config])
            if args.verbose:
                legacy_args.append("-v")
            if args.log_file:
                legacy_args.extend(["--log-file", args.log_file])
            return legacy_main(legacy_args)
    except PubMinerError as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.error(f"CLI failed: {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        logger.exception("Unexpected CLI error")
        return 1
    return 0


def main():
    """Dispatch to subcommands while preserving legacy flag-only usage."""
    known_commands = {"search", "oa-check", "oa-download", "extract", "tasks", "pipeline"}
    argv = sys.argv[1:]
    if not argv or argv[0] in {"-h", "--help"}:
        raise SystemExit(subcommand_main(argv))
    if argv[0] in known_commands:
        raise SystemExit(subcommand_main(argv))
    raise SystemExit(legacy_main(argv))


if __name__ == "__main__":
    main()
