"""Benchmark OA PDF download strategies against a fixed 10-article sample."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import aiohttp


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = WORKSPACE_ROOT / "PubMiner"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from pubminer.downloader.oa_pdf import OAPdfResolver  # noqa: E402


FIXED_SAMPLE_ARTICLES = [
    {"pmid": "41847625", "pmcid": "PMC12989549", "doi": "10.3389/fspor.2026.1719378"},
    {"pmid": "41847621", "pmcid": "PMC12990137", "doi": "10.3389/fspor.2026.1649549"},
    {"pmid": "41847618", "pmcid": "PMC12989845", "doi": "10.1016/j.isci.2026.115086"},
    {"pmid": "41847614", "pmcid": "PMC12990349", "doi": "10.1016/j.isci.2026.114733"},
    {"pmid": "41847588", "pmcid": "PMC12989554", "doi": "10.3389/fnhum.2026.1775435"},
    {"pmid": "41847434", "pmcid": "PMC12990309", "doi": "10.1093/lifemeta/loaf037"},
    {"pmid": "41847391", "pmcid": "PMC12990244", "doi": "10.2147/NSS.S578482"},
    {"pmid": "41847385", "pmcid": "PMC12989597", "doi": "10.3389/fcell.2026.1744761"},
    {"pmid": "41847381", "pmcid": "PMC12990210", "doi": "10.3389/fnbeh.2026.1689807"},
    {"pmid": "41847335", "pmcid": "PMC12990242", "doi": "10.2147/COPD.S568299"},
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,text/html;q=0.8,*/*;q=0.5",
}


async def benchmark_resolver(
    *,
    method: str,
    articles: list[dict[str, str]],
    concurrency: int,
    timeout: int,
    unpaywall_email: str | None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        resolver = OAPdfResolver(
            timeout=timeout,
            max_retries=1,
            cache_dir=tmpdir,
            unpaywall_email=unpaywall_email,
            enable_pmc=True,
            enable_unpaywall=False,
            enable_europepmc=False,
        )
        start = time.perf_counter()
        records = await resolver.download_many(articles, concurrency=concurrency)
        elapsed = time.perf_counter() - start

    return {
        "method": method,
        "elapsed_seconds": round(elapsed, 2),
        "downloaded": sum(1 for record in records if record.status == "downloaded"),
        "failed": sum(1 for record in records if record.status != "downloaded"),
        "records": [
            {
                "pmid": record.pmid,
                "pmcid": record.pmcid,
                "status": record.status,
                "source": record.source,
                "filename": record.filename,
                "error": record.error,
            }
            for record in records
        ],
    }


async def benchmark_europepmc_direct(
    *,
    articles: list[dict[str, str]],
    concurrency: int,
    timeout: int,
    mode: str,
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async def fetch_one(
        session: aiohttp.ClientSession,
        article: dict[str, str],
    ) -> dict[str, Any]:
        pmcid = article["pmcid"]
        if mode == "ptpmcrender":
            url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
        elif mode == "pdf-render":
            url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
        else:
            raise ValueError(f"Unsupported Europe PMC benchmark mode: {mode}")
        async with semaphore:
            started = time.perf_counter()
            try:
                async with session.get(url, headers=DEFAULT_HEADERS, timeout=client_timeout) as response:
                    response.raise_for_status()
                    payload = await response.read()
                is_pdf = payload.startswith(b"%PDF") and len(payload) > 1024
                return {
                    "pmid": article["pmid"],
                    "pmcid": pmcid,
                    "status": "downloaded" if is_pdf else "failed",
                    "source": f"europepmc_{mode}",
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "error": None if is_pdf else "not_pdf",
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "pmid": article["pmid"],
                    "pmcid": pmcid,
                    "status": "failed",
                    "source": f"europepmc_{mode}",
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "error": str(exc),
                }

    started = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(fetch_one(session, article) for article in articles))
    elapsed = time.perf_counter() - started

    return {
        "method": f"europepmc_{mode}",
        "elapsed_seconds": round(elapsed, 2),
        "downloaded": sum(1 for result in results if result["status"] == "downloaded"),
        "failed": sum(1 for result in results if result["status"] != "downloaded"),
        "records": results,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark OA PDF download methods on a fixed 10-article sample.")
    parser.add_argument(
        "--method",
        choices=["pmc", "europepmc-ptpmcrender", "europepmc-pdf-render", "all"],
        default="all",
        help="Which benchmark method to run.",
    )
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent downloads to allow.")
    parser.add_argument("--timeout", type=int, default=45, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--unpaywall-email",
        default=None,
        help="Optional Unpaywall email; unused by default because the fixed benchmark isolates direct methods.",
    )
    args = parser.parse_args()

    methods = []
    if args.method in {"pmc", "all"}:
        methods.append(
            benchmark_resolver(
                method="pmc_oa_api",
                articles=FIXED_SAMPLE_ARTICLES,
                concurrency=args.concurrency,
                timeout=args.timeout,
                unpaywall_email=args.unpaywall_email,
            )
        )
    if args.method in {"europepmc-ptpmcrender", "all"}:
        methods.append(
            benchmark_europepmc_direct(
                articles=FIXED_SAMPLE_ARTICLES,
                concurrency=args.concurrency,
                timeout=args.timeout,
                mode="ptpmcrender",
            )
        )
    if args.method in {"europepmc-pdf-render", "all"}:
        methods.append(
            benchmark_europepmc_direct(
                articles=FIXED_SAMPLE_ARTICLES,
                concurrency=args.concurrency,
                timeout=args.timeout,
                mode="pdf-render",
            )
        )

    results = await asyncio.gather(*methods)
    print(
        json.dumps(
            {
                "sample_size": len(FIXED_SAMPLE_ARTICLES),
                "concurrency": args.concurrency,
                "timeout_seconds": args.timeout,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
