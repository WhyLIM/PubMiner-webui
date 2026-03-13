"""
Main CLI entry point for PubMiner.

Provides command-line interface for running the literature mining pipeline.
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List

import aiohttp
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from pubminer.core.config import Config
from pubminer.core.state import StateManager, ProcessingStage
from pubminer.core.logger import setup_logger, get_logger
from pubminer.core.exceptions import PubMinerError
from pubminer.fetcher.pubmed_client import AsyncPubMedClient
from pubminer.downloader.pmc_bioc import BioCAPIClient
from pubminer.downloader.section_parser import SectionType
from pubminer.extractor.zhipu_client import ZhipuExtractor
from pubminer.extractor.schemas.base_info import BaseExtractionModel
from pubminer.extractor.schemas.custom import DynamicSchemaBuilder
from pubminer.exporter.csv_writer import CSVExporter

console = Console()
logger = None  # Will be initialized in main()


async def run_pipeline(
    config: Config,
    query: Optional[str] = None,
    pmid_file: Optional[str] = None,
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
        if pmid_file:
            console.print(f"[cyan]Loading PMIDs from file:[/cyan] {pmid_file}")
            with open(pmid_file, "r") as f:
                pmids = [line.strip() for line in f if line.strip().isdigit()]
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Searching PubMed...", total=None)
                pmids = await pubmed_client.search(
                    query,
                    max_results=config.search.max_results,
                )

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

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
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

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
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


if __name__ == "__main__":
    main()
