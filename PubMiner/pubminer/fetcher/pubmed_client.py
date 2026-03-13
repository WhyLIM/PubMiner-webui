"""
Async PubMed client using Biopython Entrez.

Wraps synchronous Biopython calls with asyncio.to_thread() for non-blocking operation.
"""

import asyncio
import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from Bio import Entrez
from Bio.Entrez import Parser

from pubminer.core.exceptions import PubMedAPIError
from pubminer.core.logger import get_logger
from pubminer.fetcher.models import LiteratureMetadata

logger = get_logger("fetcher")


class AsyncPubMedClient:
    """
    Asynchronous PubMed client.

    Uses Biopython's Entrez module wrapped in asyncio.to_thread()
    for non-blocking PubMed searches and metadata retrieval.
    """

    def __init__(
        self,
        email: str,
        api_key: Optional[str] = None,
        tool_name: str = "PubMiner",
        rate_limit: float = 0.34,
    ):
        """
        Initialize the PubMed client.

        Args:
            email: Email address (required by NCBI)
            api_key: NCBI API key for higher rate limits
            tool_name: Tool name for NCBI tracking
            rate_limit: Seconds between requests
        """
        Entrez.email = email
        Entrez.tool = tool_name

        if api_key:
            Entrez.api_key = api_key
            self.rate_limit = 0.1  # 10 req/s with key
        else:
            self.rate_limit = rate_limit

        self._last_request_time = 0.0
        self._request_lock = asyncio.Lock()
        self.last_citation_report: Dict[str, Any] = {
            "enabled": False,
            "status": "disabled",
            "message": "Citation fetching was not requested.",
            "cited_by_status": "disabled",
            "references_status": "disabled",
            "cited_by_total": 0,
            "references_total": 0,
        }

        logger.info(
            f"Initialized PubMed client (rate_limit={self.rate_limit}s, api_key={'yes' if api_key else 'no'})"
        )

    async def _rate_limited_call(self, func, *args, **kwargs) -> Any:
        """
        Execute a rate-limited Entrez API call.

        Wraps synchronous Biopython calls in asyncio.to_thread()
        and enforces rate limiting.
        """
        async with self._request_lock:
            # Enforce rate limit
            elapsed = asyncio.get_event_loop().time() - self._last_request_time
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)

            try:
                result = await asyncio.to_thread(func, *args, **kwargs)
                self._last_request_time = asyncio.get_event_loop().time()
                return result
            except Exception as e:
                logger.error(f"Entrez API error: {e}")
                raise PubMedAPIError(str(e))

    async def search(
        self,
        query: str,
        max_results: int = 100,
        offset: int = 0,
        date_range: Optional[tuple] = None,
        use_history: bool = True,
    ) -> Dict[str, Any]:
        """
        Search PubMed and return a list of PMIDs.

        Args:
            query: PubMed search query
            max_results: Maximum number of results
            date_range: Tuple of (start_date, end_date) in YYYY/MM/DD format
            use_history: Use NCBI history server for large result sets

        Returns:
            Dict with PMIDs and search metadata
        """
        logger.info(f"Searching PubMed: '{query}' (offset={offset}, max={max_results})")

        search_args = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retstart": offset,
            "usehistory": "y" if use_history else "n",
        }

        if date_range:
            search_args["mindate"] = date_range[0]
            search_args["maxdate"] = date_range[1]

        try:
            handle = await self._rate_limited_call(Entrez.esearch, **search_args)
            record = Entrez.read(handle)
            handle.close()

            pmids = record.get("IdList", [])
            total_count = int(record.get("Count", 0))

            logger.info(f"Found {total_count} results, returning {len(pmids)} PMIDs")

            return {
                "pmids": pmids,
                "total_count": total_count,
                "offset": offset,
                "returned_count": len(pmids),
            }

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise PubMedAPIError(f"Search failed: {e}")

    async def fetch_metadata(
        self,
        pmids: List[str],
        batch_size: int = 200,
        include_citations: bool = False,
    ) -> List[LiteratureMetadata]:
        """
        Fetch metadata for a list of PMIDs.

        Args:
            pmids: List of PubMed IDs
            batch_size: Number of PMIDs per batch
            include_citations: Whether to fetch cited-by/reference links

        Returns:
            List of LiteratureMetadata objects
        """
        if not pmids:
            return []

        logger.info(f"Fetching metadata for {len(pmids)} PMIDs (batch_size={batch_size})")

        results = []
        total_batches = (len(pmids) + batch_size - 1) // batch_size

        for i in range(0, len(pmids), batch_size):
            batch_num = i // batch_size + 1
            batch = pmids[i : i + batch_size]

            logger.debug(f"Processing batch {batch_num}/{total_batches}")

            try:
                handle = await self._rate_limited_call(
                    Entrez.efetch,
                    db="pubmed",
                    id=",".join(batch),
                    rettype="xml",
                    retmode="xml",
                )

                data = Entrez.read(handle)
                handle.close()

                # Entrez.read() returns a dict with 'PubmedArticle' and 'PubmedBookArticle' keys
                records = data.get("PubmedArticle", [])

                for record in records:
                    try:
                        metadata = self._parse_pubmed_record(record)
                        results.append(metadata)
                    except Exception as e:
                        pmid = self._extract_pmid_from_record(record)
                        logger.warning(f"Failed to parse record {pmid}: {e}")

            except Exception as e:
                logger.error(f"Failed to fetch batch {batch_num}: {e}")
                # Continue with remaining batches

        logger.info(f"Successfully parsed {len(results)} records")

        # Fetch citation data only when requested
        if results and include_citations:
            logger.info("Fetching citation data...")
            pmid_list = [m.pmid for m in results]
            citation_data = await self.fetch_citation_data(pmid_list)

            # Update metadata with citation information
            for metadata in results:
                if metadata.pmid in citation_data:
                    data = citation_data[metadata.pmid]
                    metadata.cited_count = data["cited_count"]
                    metadata.cited_by = data["cited_by"]
                    metadata.references_count = data["references_count"]
                    metadata.references = data["references"]
        elif not include_citations:
            self.last_citation_report = {
                "enabled": False,
                "status": "disabled",
                "message": "Citation fetching was not requested.",
                "cited_by_status": "disabled",
                "references_status": "disabled",
                "cited_by_total": 0,
                "references_total": 0,
            }

        return results

    def _parse_pubmed_record(self, record: Dict) -> LiteratureMetadata:
        """Parse a single PubMed XML record into LiteratureMetadata."""

        # Extract PMID
        pmid = self._extract_pmid_from_record(record)

        # Extract Article
        article = record.get("MedlineCitation", {}).get("Article", {})

        # Title
        title = article.get("ArticleTitle", "")
        if isinstance(title, list):
            title = " ".join(str(t) for t in title)

        # Authors
        authors = []
        first_author = ""
        affiliation = ""
        author_list = article.get("AuthorList", [])
        if author_list:
            for idx, author in enumerate(author_list):
                if isinstance(author, dict):
                    last = author.get("LastName", "")
                    fore = author.get("ForeName", "") or author.get("Initials", "")
                    if last:
                        author_name = f"{last} {fore}".strip()
                        authors.append(author_name)
                        if idx == 0:
                            first_author = author_name
                            # Get affiliation from first author
                            aff_info = author.get("AffiliationInfo", [])
                            if aff_info and isinstance(aff_info, list):
                                affiliation = aff_info[0].get("Affiliation", "") if isinstance(aff_info[0], dict) else ""

        # Journal
        journal_info = article.get("Journal", {})
        journal = journal_info.get("Title", "")
        journal_abbrev = journal_info.get("ISOAbbreviation", "")
        issn = journal_info.get("ISSN", "")
        journal_id = journal_info.get("JournalIssue", {}).get("Issue", "")

        # Publication date
        pub_date = None
        year = None

        # Try JournalIssue date
        journal_issue = journal_info.get("JournalIssue", {})
        pub_date_obj = journal_issue.get("PubDate", {})
        if pub_date_obj:
            year = int(pub_date_obj.get("Year", 0)) or None
            if year:
                pub_date = f"{year}"
                medline_date = pub_date_obj.get("MedlineDate", "")
                if medline_date:
                    pub_date = medline_date

        # Volume and pages
        volume = journal_issue.get("Volume", "")
        issue = journal_issue.get("Issue", "")
        pagination = article.get("Pagination", {})
        pages = pagination.get("MedlinePgn", "")

        # Abstract
        abstract_parts = []
        abstract = article.get("Abstract", {})
        if abstract:
            for text in abstract.get("AbstractText", []):
                if isinstance(text, str):
                    abstract_parts.append(text)
                elif isinstance(text, dict):
                    # Structured abstract
                    label = text.get("Label", "")
                    content = text.get("_", "")
                    if label and content:
                        abstract_parts.append(f"{label}: {content}")
                    elif content:
                        abstract_parts.append(content)
        abstract_text = " ".join(abstract_parts)

        # Keywords
        keywords = []
        keyword_list = record.get("MedlineCitation", {}).get("KeywordList", [])
        for kw_list in keyword_list:
            for kw in kw_list:
                if isinstance(kw, str):
                    keywords.append(kw)

        # MeSH terms
        mesh_terms = []
        mesh_list = record.get("MedlineCitation", {}).get("MeshHeadingList", [])
        for mesh in mesh_list:
            descriptor = mesh.get("DescriptorName", "")
            if isinstance(descriptor, dict):
                mesh_terms.append(descriptor.get("_", str(descriptor)))
            elif descriptor:
                mesh_terms.append(str(descriptor))

        # Language
        language_list = article.get("Language", [])
        language = self._coerce_pubmed_value(language_list[0]) if language_list else ""

        # Article type
        publication_types = article.get("PublicationTypeList", [])
        article_type = self._coerce_pubmed_value(publication_types[0]) if publication_types else ""

        # Status and revision date
        medline_status = self._coerce_pubmed_value(
            record.get("MedlineCitation", {}).get("Status", "")
        )
        publication_status = self._coerce_pubmed_value(
            record.get("PubmedData", {}).get("PublicationStatus", "")
        )
        status = publication_status or medline_status
        last_revision_date = self._extract_last_revision_date(
            record.get("PubmedData", {}).get("History", [])
        )

        # Grant list
        grant_list = ""
        grants = article.get("GrantList", [])
        if grants:
            grant_strs = []
            for grant in grants:
                if isinstance(grant, dict):
                    agency = grant.get("Agency", "")
                    grant_id = grant.get("GrantID", "")
                    if agency or grant_id:
                        grant_strs.append(f"{agency}: {grant_id}".strip(": "))
            grant_list = "; ".join(grant_strs)

        # DOI and PMCID
        doi = None
        pmcid = None
        has_pmc_fulltext = False

        article_ids = record.get("PubmedData", {}).get("ArticleIdList", [])
        for aid in article_ids:
            aid_type = aid.attributes.get("IdType", "")
            aid_value = str(aid)

            if aid_type == "doi":
                doi = aid_value
            elif aid_type == "pmc":
                pmcid = aid_value
                has_pmc_fulltext = True

        # Also check for PMCID in OtherID
        other_ids = record.get("PubmedData", {}).get("OtherID", [])
        for other_id in other_ids:
            if str(other_id).startswith("PMC"):
                pmcid = str(other_id)
                has_pmc_fulltext = True

        return LiteratureMetadata(
            pmid=pmid,
            pmcid=pmcid,
            doi=doi,
            title=title,
            authors=authors,
            first_author=first_author,
            affiliation=affiliation,
            journal=journal,
            journal_abbrev=journal_abbrev,
            issn=issn,
            journal_id=journal_id,
            pub_date=pub_date,
            year=year,
            volume=volume,
            issue=issue,
            pages=pages,
            publication_status=publication_status,
            article_type=article_type,
            abstract=abstract_text,
            keywords=keywords,
            mesh_terms=mesh_terms,
            language=language,
            status=status,
            last_revision_date=last_revision_date,
            grant_list=grant_list,
            has_pmc_fulltext=has_pmc_fulltext,
        )

    def _coerce_pubmed_value(self, value: Any) -> str:
        """Convert PubMed parser objects to a clean string."""
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, dict):
            direct = value.get("_")
            if direct:
                return str(direct).strip()

        text = str(value).strip()
        return "" if text in {"None", "{}"} else text

    def _extract_last_revision_date(self, history: Any) -> str:
        """Extract the best available revision date from PubMed history."""
        if not isinstance(history, list) or not history:
            return ""

        normalized_dates = []
        for entry in history:
            if not isinstance(entry, dict):
                continue

            pub_status = self._coerce_pubmed_value(entry.get("PubStatus", "")).lower()
            formatted = self._format_pubmed_date(entry)
            if not formatted:
                continue

            normalized_dates.append((pub_status, formatted))

        if not normalized_dates:
            return ""

        for pub_status, formatted in normalized_dates:
            if pub_status == "revised":
                return formatted

        return normalized_dates[-1][1]

    def _format_pubmed_date(self, date_entry: Dict[str, Any]) -> str:
        """Format a PubMed history date entry as YYYY-MM-DD when possible."""
        year = self._coerce_pubmed_value(date_entry.get("Year", ""))
        month = self._normalize_pubmed_month(self._coerce_pubmed_value(date_entry.get("Month", "")))
        day = self._extract_numeric_component(self._coerce_pubmed_value(date_entry.get("Day", "")))

        if not year:
            return ""

        if month and day:
            return f"{year}-{month}-{day}"
        if month:
            return f"{year}-{month}"
        return year

    def _normalize_pubmed_month(self, month_value: str) -> str:
        """Normalize PubMed month values like Jan or 3 to two-digit numbers."""
        if not month_value:
            return ""

        month_map = {
            "jan": "01",
            "feb": "02",
            "mar": "03",
            "apr": "04",
            "may": "05",
            "jun": "06",
            "jul": "07",
            "aug": "08",
            "sep": "09",
            "sept": "09",
            "oct": "10",
            "nov": "11",
            "dec": "12",
        }

        lowered = month_value.lower()
        if lowered[:3] in month_map:
            return month_map[lowered[:3]]

        numeric = self._extract_numeric_component(month_value)
        return numeric

    def _extract_numeric_component(self, value: str) -> str:
        """Extract the first numeric component and pad it to two digits."""
        if not value:
            return ""

        match = re.search(r"\d{1,2}", value)
        if not match:
            return ""

        return match.group(0).zfill(2)

    def _extract_pmid_from_record(self, record: Dict) -> str:
        """Extract PMID from a PubMed record."""
        # Try MedlineCitation first
        pmid = record.get("MedlineCitation", {}).get("PMID", "")
        if pmid:
            return str(pmid)

        # Try PubmedData
        article_ids = record.get("PubmedData", {}).get("ArticleIdList", [])
        for aid in article_ids:
            if aid.attributes.get("IdType") == "pubmed":
                return str(aid)

        return ""

    async def get_pmcid(self, pmid: str) -> Optional[str]:
        """
        Get PMCID for a single PMID using ELink.

        Args:
            pmid: PubMed ID

        Returns:
            PMCID or None
        """
        try:
            handle = await self._rate_limited_call(
                Entrez.elink,
                dbfrom="pubmed",
                db="pmc",
                id=pmid,
                linkname="pubmed_pmc",
            )
            record = Entrez.read(handle)
            handle.close()

            for linkset in record:
                for linksetdb in linkset.get("LinkSetDb", []):
                    for link in linksetdb.get("Link", []):
                        return f"PMC{link.get('Id', '')}"

            return None

        except Exception as e:
            logger.warning(f"Failed to get PMCID for {pmid}: {e}")
            return None

    async def fetch_citation_data(
        self,
        pmids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch citation and reference data for multiple PMIDs.

        Args:
            pmids: List of PubMed IDs

        Returns:
            Dictionary mapping PMID to citation data:
            {
                "pmid": {
                    "cited_count": int,
                    "cited_by": List[str],
                    "references_count": int,
                    "references": List[str]
                }
            }
        """
        if not pmids:
            return {}

        logger.info(f"Fetching citation data for {len(pmids)} PMIDs")
        self.last_citation_report = {
            "enabled": True,
            "status": "running",
            "message": f"Fetching citation links for {len(pmids)} PMIDs.",
            "cited_by_status": "pending",
            "references_status": "pending",
            "cited_by_total": 0,
            "references_total": 0,
        }

        citation_data = {
            pmid: {
                "cited_count": 0,
                "cited_by": [],
                "references_count": 0,
                "references": []
            }
            for pmid in pmids
        }

        try:
            async def fetch_link_map(linkname: str) -> Dict[str, List[str]]:
                handle = await self._rate_limited_call(
                    Entrez.elink,
                    dbfrom="pubmed",
                    db="pubmed",
                    id=",".join(pmids),
                    linkname=linkname,
                    retmode="xml",
                    cmd="neighbor",
                )
                records = Entrez.read(handle)
                handle.close()

                link_map: Dict[str, List[str]] = {}
                for i, record in enumerate(records):
                    pmid = pmids[i] if i < len(pmids) else None
                    if not pmid:
                        continue

                    ids: List[str] = []
                    for linkset in record.get("LinkSetDb", []):
                        if linkset.get("LinkName") != linkname:
                            continue
                        ids.extend(link["Id"] for link in linkset.get("Link", []) if link.get("Id"))
                    link_map[pmid] = ids

                return link_map

            try:
                cited_map = await fetch_link_map("pubmed_pubmed_citedin")
                self.last_citation_report["cited_by_status"] = "success"
            except Exception as e:
                logger.warning(f"Failed to fetch cited-by links: {e}")
                cited_map = {}
                self.last_citation_report["cited_by_status"] = "failed"

            try:
                refs_map = await fetch_link_map("pubmed_pubmed_refs")
                self.last_citation_report["references_status"] = "success"
            except Exception as e:
                logger.warning(f"Failed to fetch reference links: {e}")
                refs_map = {}
                self.last_citation_report["references_status"] = "failed"

            for pmid in pmids:
                cited_by = cited_map.get(pmid, [])
                references = refs_map.get(pmid, [])
                citation_data[pmid] = {
                    "cited_count": len(cited_by),
                    "cited_by": cited_by,
                    "references_count": len(references),
                    "references": references,
                }

            self.last_citation_report["cited_by_total"] = sum(
                item["cited_count"] for item in citation_data.values()
            )
            self.last_citation_report["references_total"] = sum(
                item["references_count"] for item in citation_data.values()
            )
            if (
                self.last_citation_report["cited_by_status"] == "success"
                and self.last_citation_report["references_status"] == "success"
            ):
                self.last_citation_report["status"] = "success"
                self.last_citation_report["message"] = "Citation counts and reference links loaded."
            elif (
                self.last_citation_report["cited_by_status"] == "failed"
                and self.last_citation_report["references_status"] == "failed"
            ):
                self.last_citation_report["status"] = "failed"
                self.last_citation_report["message"] = "Citation requests failed. Counts were left empty."
            else:
                self.last_citation_report["status"] = "partial"
                self.last_citation_report["message"] = "Citation data loaded partially."

            logger.info(f"Successfully fetched citation data for {len(citation_data)} PMIDs")
            return citation_data

        except Exception as e:
            logger.error(f"Failed to fetch citation data: {e}")
            self.last_citation_report = {
                "enabled": True,
                "status": "failed",
                "message": str(e),
                "cited_by_status": "failed",
                "references_status": "failed",
                "cited_by_total": 0,
                "references_total": 0,
            }
            return citation_data

    async def close(self):
        """Close any open connections."""
        # Biopython Entrez doesn't maintain persistent connections
        pass
