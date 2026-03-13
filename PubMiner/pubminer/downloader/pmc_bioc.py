"""
NCBI BioC API client for retrieving full-text articles.

Provides async access to PMC Open Access articles in BioC format.
"""

import aiohttp
import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

from pubminer.core.exceptions import BioCAPIError
from pubminer.core.logger import get_logger
from pubminer.downloader.section_parser import BioCSectionParser, SectionType
from pubminer.downloader.models import FullTextDocument

logger = get_logger("downloader")


class BioCAPIClient:
    """
    Async client for NCBI BioC API.

    Retrieves full-text articles from PMC Open Access Subset in BioC JSON format.
    """

    BASE_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        keep_sections: Optional[List[SectionType]] = None,
        cache_dir: Optional[str] = None,
        use_cache: bool = True,
    ):
        """
        Initialize the BioC API client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
            keep_sections: Section types to keep for extraction
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.parser = BioCSectionParser(keep_sections=keep_sections)
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir or "download/pmc_cache")
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"BioC client initialized (timeout={timeout}s, retries={max_retries})")

    def _get_cache_path(self, pmcid: str) -> Path:
        normalized_pmcid = pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"
        return self.cache_dir / f"{normalized_pmcid}.json"

    def _load_cached_document(self, pmcid: str, pmid: str = "") -> Tuple[Optional[FullTextDocument], Dict[str, Any]]:
        if not self.use_cache:
            return None, {}

        cache_path = self._get_cache_path(pmcid)
        if not cache_path.exists():
            return None, {}

        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            document = FullTextDocument(
                pmid=pmid or cached.get("pmid", ""),
                pmcid=cached.get("pmcid", pmcid),
                raw_bioc=None,
                filtered_text=cached.get("filtered_text", ""),
                sections=cached.get("sections", {}),
                title=cached.get("title", ""),
            )
            document.estimate_tokens()
            status = {
                "pmcid": document.pmcid,
                "pmid": document.pmid,
                "status": "success",
                "reason": "cache_hit",
                "message": "Loaded full text from local cache",
                "used_fallback": cached.get("used_fallback", False),
                "cached": True,
            }
            return document, status
        except Exception as e:
            logger.warning(f"Failed to read cache for {pmcid}: {e}")
            return None, {}

    def _save_cached_document(self, document: FullTextDocument, used_fallback: bool) -> None:
        if not self.use_cache:
            return

        cache_path = self._get_cache_path(document.pmcid)
        payload = {
            "pmid": document.pmid,
            "pmcid": document.pmcid,
            "title": document.title,
            "filtered_text": document.filtered_text,
            "sections": document.sections,
            "used_fallback": used_fallback,
            "cached_at": datetime.utcnow().isoformat(),
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    async def fetch_fulltext(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
        output_format: str = "json",
    ) -> Optional[Dict]:
        """
        Fetch full-text article in BioC format.

        Args:
            session: aiohttp ClientSession
            pmcid: PMC ID (with or without 'PMC' prefix)
            output_format: 'json' or 'xml'

        Returns:
            BioC JSON data or None if not available
        """
        # Normalize PMCID
        if not pmcid.upper().startswith("PMC"):
            pmcid = f"PMC{pmcid}"

        url = f"{self.BASE_URL}/BioC_{output_format}/{pmcid}/unicode"

        for attempt in range(self.max_retries):
            try:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        # Check content type
                        content_type = response.headers.get('Content-Type', '')
                        
                        if 'json' in content_type:
                            if output_format == "json":
                                return await response.json()
                            else:
                                return await response.text()
                        elif 'html' in content_type:
                            # Not available in PMC OA Subset
                            logger.debug(f"PMCID {pmcid} not available in PMC OA Subset (HTML response)")
                            return None
                        else:
                            # Try to parse as JSON anyway
                            try:
                                if output_format == "json":
                                    return await response.json()
                                else:
                                    return await response.text()
                            except Exception:
                                logger.debug(f"PMCID {pmcid} returned unexpected content type: {content_type}")
                                return None

                    elif response.status == 404:
                        # Article not in PMC OA Subset
                        logger.debug(f"PMCID {pmcid} not found in PMC OA Subset")
                        return None

                    elif response.status == 429:
                        # Rate limited
                        retry_after = float(response.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limited, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    else:
                        raise BioCAPIError(
                            f"BioC API error: HTTP {response.status}",
                            pmcid=pmcid,
                            status_code=response.status,
                        )

            except aiohttp.ClientError as e:
                logger.warning(f"Request failed for {pmcid} (attempt {attempt + 1}): {e}")

                if attempt == self.max_retries - 1:
                    raise BioCAPIError(
                        f"Failed to fetch {pmcid} after {self.max_retries} attempts: {e}",
                        pmcid=pmcid,
                    )

                # Exponential backoff
                await asyncio.sleep(2 ** attempt)

        return None

    async def get_filtered_document_with_status(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
        pmid: str = "",
    ) -> Tuple[Optional[FullTextDocument], Dict[str, Any]]:
        """
        Get a filtered full-text document ready for LLM extraction with status details.

        Args:
            session: aiohttp ClientSession
            pmcid: PMC ID
            pmid: PubMed ID (for reference)

        Returns:
            Tuple of FullTextDocument or None and a structured status payload
        """
        normalized_pmcid = pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"
        status: Dict[str, Any] = {
            "pmcid": normalized_pmcid,
            "pmid": pmid,
            "status": "failed",
            "reason": "unknown",
            "message": "",
            "used_fallback": False,
            "cached": False,
        }

        cached_document, cached_status = self._load_cached_document(normalized_pmcid, pmid)
        if cached_document is not None:
            return cached_document, cached_status

        try:
            bioc_data = await self.fetch_fulltext(session, normalized_pmcid)
        except BioCAPIError as e:
            status["reason"] = "request_failed"
            status["message"] = str(e)
            logger.warning(f"Full-text request failed for {normalized_pmcid}: {e}")
            return None, status

        if not bioc_data:
            status["reason"] = "not_available"
            status["message"] = "PMCID not available in PMC OA BioC response"
            return None, status

        try:
            # Extract title
            title = self._extract_title(bioc_data)

            # Get filtered text
            filtered_text = self.parser.get_filtered_text(bioc_data)

            if not filtered_text:
                logger.warning(
                    f"No structured sections extracted for {normalized_pmcid}; falling back to best-effort full text"
                )
                filtered_text = self.parser.get_fallback_text(bioc_data)
                status["used_fallback"] = True

            if not filtered_text:
                logger.warning(f"No fallback full text extracted for {normalized_pmcid}")
                status["reason"] = "empty_content"
                status["message"] = "BioC article did not contain usable body text after filtering"
                return None, status

            # Get sections
            sections = self.parser.parse_bioc_document(bioc_data)
            sections_dict = {st.value: text for st, text in sections.items()}

            doc = FullTextDocument(
                pmid=pmid,
                pmcid=normalized_pmcid,
                raw_bioc=bioc_data,
                filtered_text=filtered_text,
                sections=sections_dict,
                title=title,
            )

            doc.estimate_tokens()

            logger.debug(
                f"Processed {normalized_pmcid}: {doc.total_chars} chars, ~{doc.total_tokens_estimate} tokens"
            )

            status["status"] = "success"
            status["reason"] = "fallback_used" if status["used_fallback"] else "structured_sections"
            status["message"] = (
                "Downloaded with best-effort fallback text"
                if status["used_fallback"]
                else "Downloaded with structured section filtering"
            )
            self._save_cached_document(doc, status["used_fallback"])
            return doc, status

        except Exception as e:
            logger.error(f"Failed to process BioC data for {normalized_pmcid}: {e}")
            status["reason"] = "parse_error"
            status["message"] = str(e)
            return None, status

    async def get_filtered_document(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
        pmid: str = "",
    ) -> Optional[FullTextDocument]:
        """Backward-compatible wrapper that returns only the document."""
        document, _ = await self.get_filtered_document_with_status(session, pmcid, pmid)
        return document

    def _extract_title(self, bioc_data: Dict) -> str:
        """Extract article title from BioC data."""
        try:
            # Handle BioC response format (list containing collection)
            if isinstance(bioc_data, list):
                if not bioc_data:
                    return ""
                bioc_data = bioc_data[0]

            documents = bioc_data.get("documents", [])
            if documents:
                passages = documents[0].get("passages", [])
                for passage in passages:
                    infons = passage.get("infons", {})
                    if infons.get("type") == "title":
                        return passage.get("text", "")
        except Exception:
            pass
        return ""

    async def batch_download(
        self,
        pmcids: List[str],
        pmids: Optional[List[str]] = None,
        concurrency: int = 5,
    ) -> List[FullTextDocument]:
        """
        Batch download full-text documents.

        Args:
            pmcids: List of PMC IDs
            pmids: Optional corresponding PubMed IDs
            concurrency: Maximum concurrent requests

        Returns:
            List of FullTextDocument objects
        """
        semaphore = asyncio.Semaphore(concurrency)
        pmid_map = dict(zip(pmcids, pmids or []))

        async with aiohttp.ClientSession() as session:

            async def limited_download(pmcid: str) -> Optional[FullTextDocument]:
                async with semaphore:
                    pmid = pmid_map.get(pmcid, "")
                    return await self.get_filtered_document(session, pmcid, pmid)

            tasks = [limited_download(pmcid) for pmcid in pmcids]
            results = await asyncio.gather(*tasks)

        # Filter out None results
        documents = [doc for doc in results if doc is not None]

        logger.info(f"Successfully downloaded {len(documents)}/{len(pmcids)} full-text documents")

        return documents

    async def batch_download_with_report(
        self,
        pmcids: List[str],
        pmids: Optional[List[str]] = None,
        concurrency: int = 5,
    ) -> Tuple[List[FullTextDocument], Dict[str, Any]]:
        """
        Batch download full-text documents and return a structured report.

        Returns:
            Tuple of downloaded documents and a report dict for UI/task diagnostics
        """
        semaphore = asyncio.Semaphore(concurrency)
        pmid_map = dict(zip(pmcids, pmids or []))

        async with aiohttp.ClientSession() as session:

            async def limited_download(pmcid: str) -> Tuple[Optional[FullTextDocument], Dict[str, Any]]:
                async with semaphore:
                    pmid = pmid_map.get(pmcid, "")
                    return await self.get_filtered_document_with_status(session, pmcid, pmid)

            tasks = [limited_download(pmcid) for pmcid in pmcids]
            results = await asyncio.gather(*tasks)

        documents = [doc for doc, _ in results if doc is not None]
        statuses = [status for _, status in results]
        failed_items = [item for item in statuses if item["status"] != "success"]
        fallback_items = [item for item in statuses if item["status"] == "success" and item["used_fallback"]]
        cache_hits = [item for item in statuses if item["status"] == "success" and item.get("cached")]

        reasons = {
            "request_failed": "Network or NCBI request failed",
            "not_available": "PMC BioC full text unavailable",
            "empty_content": "Full text fetched but no usable body text remained",
            "parse_error": "BioC document parsing failed",
        }

        failure_counts: Dict[str, int] = {}
        for item in failed_items:
            failure_counts[item["reason"]] = failure_counts.get(item["reason"], 0) + 1

        report = {
            "pmc_candidates": len(pmcids),
            "downloaded": len(documents),
            "failed": len(failed_items),
            "fallback_used": len(fallback_items),
            "cache_hits": len(cache_hits),
            "cache_misses": max(len(pmcids) - len(cache_hits), 0),
            "failure_counts": failure_counts,
            "failure_labels": {key: reasons.get(key, key) for key in failure_counts},
            "items": statuses,
            "failed_items": failed_items[:10],
        }

        logger.info(
            "Full-text report: %s downloaded, %s failed, %s fallback, %s cache hits",
            report["downloaded"],
            report["failed"],
            report["fallback_used"],
            report["cache_hits"],
        )

        return documents, report

    async def check_availability(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
    ) -> bool:
        """
        Check if a PMCID has full-text available.

        Args:
            session: aiohttp ClientSession
            pmcid: PMC ID

        Returns:
            True if available
        """
        try:
            result = await self.fetch_fulltext(session, pmcid)
            return result is not None
        except Exception:
            return False
