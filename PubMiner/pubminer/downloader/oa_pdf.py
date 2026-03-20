"""Resolver and downloader for legal open-access PDFs."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import tempfile
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

import aiohttp

from pubminer.core.logger import get_logger
from pubminer.downloader.oa_pdf_models import OAPdfCandidate, OAPdfDownloadRecord, OAPdfResolution

logger = get_logger("oa_pdf")
DEFAULT_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,text/html;q=0.8,*/*;q=0.5",
}
MAX_PDF_SIZE_BYTES = 100 * 1024 * 1024
PMC_OA_API_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


class AnchorCollector(HTMLParser):
    """Collect anchor tags and their text from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self._current_href: Optional[str] = None
        self._current_attrs: Dict[str, str] = {}
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        self._current_href = attrs_dict.get("href")
        self._current_attrs = attrs_dict
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        self.links.append(
            {
                "href": self._current_href,
                "text": "".join(self._current_text).strip(),
                "aria_label": self._current_attrs.get("aria-label", "").strip(),
            }
        )
        self._current_href = None
        self._current_attrs = {}
        self._current_text = []


class OAPdfResolver:
    """Resolve and download legal OA PDFs from supported providers."""

    def __init__(
        self,
        *,
        timeout: int = 30,
        max_retries: int = 3,
        prefer_pmc: bool = True,
        strict_oa: bool = True,
        cache_dir: str = "download/pdf_cache",
        cache_only_when_license_known: bool = True,
        unpaywall_email: Optional[str] = None,
        enable_pmc: bool = True,
        enable_unpaywall: bool = True,
    ) -> None:
        self.timeout_seconds = timeout
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.prefer_pmc = prefer_pmc
        self.strict_oa = strict_oa
        self.cache_only_when_license_known = cache_only_when_license_known
        self.unpaywall_email = unpaywall_email
        self.enable_pmc = enable_pmc
        self.enable_unpaywall = enable_unpaywall
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.cache_dir / "manifest.jsonl"

    async def resolve_many(self, articles: List[Dict[str, Any]]) -> List[OAPdfResolution]:
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            return [await self.resolve_article(session, article) for article in articles]

    async def resolve_article(
        self,
        session: aiohttp.ClientSession,
        article: Dict[str, Any],
    ) -> OAPdfResolution:
        pmid = str(article.get("pmid") or "").strip()
        doi = self._normalize_doi(article.get("doi"))
        pmcid = self._normalize_pmcid(article.get("pmcid"))
        candidates: List[OAPdfCandidate] = []
        reasons: List[str] = []

        if self.enable_pmc and pmcid:
            try:
                candidates.extend(await self._resolve_pmc_candidates(session, pmcid))
            except Exception as exc:
                logger.warning("PMC OA API lookup failed for %s: %s", pmcid, exc)
                candidates.append(self._build_pmc_fallback_candidate(pmcid))
                reasons.append("PMC OA API lookup failed; falling back to PMC article page")

        if self.enable_unpaywall and doi and self.unpaywall_email:
            try:
                unpaywall_candidates = await self._resolve_unpaywall(session, doi)
                candidates.extend(unpaywall_candidates)
            except Exception as exc:
                logger.warning("Unpaywall lookup failed for %s: %s", doi, exc)
                reasons.append("Unpaywall lookup failed")
        elif self.enable_unpaywall and doi and not self.unpaywall_email:
            reasons.append("Unpaywall email is not configured")
        elif not doi and not pmcid:
            reasons.append("No DOI or PMCID was provided")

        for candidate in candidates:
            if candidate.can_download or not candidate.landing_page_url or not self._is_legal_landing_page(candidate):
                continue
            try:
                resolved_pdf_url = await self._resolve_pdf_from_landing_page(session, candidate)
            except Exception as exc:
                logger.debug("Landing page PDF resolution failed for %s: %s", candidate.landing_page_url, exc)
                continue
            if resolved_pdf_url:
                candidate.pdf_url = resolved_pdf_url
                candidate.can_download = True
                candidate.evidence = f"{candidate.evidence}; direct PDF link extracted from landing page"
                candidate.score += 8.0

        best_candidate = self._choose_best_candidate(candidates)
        has_non_downloadable_candidate = any(candidate for candidate in candidates if not candidate.can_download)
        if best_candidate and best_candidate.can_download:
            availability = "available"
        elif has_non_downloadable_candidate:
            availability = "ambiguous"
        else:
            availability = "unavailable"
        reason = (
            best_candidate.evidence
            if best_candidate and best_candidate.can_download
            else "; ".join(filter(None, reasons)) or "No legal OA PDF source was found"
        )

        return OAPdfResolution(
            pmid=pmid,
            doi=doi,
            pmcid=pmcid,
            availability=availability,
            best_candidate=best_candidate,
            candidates=candidates,
            reason=reason,
            resolved_at=self._utc_now(),
        )

    async def download_best(self, article: Dict[str, Any]) -> OAPdfDownloadRecord:
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            resolution = await self.resolve_article(session, article)
            downloadable_candidates = sorted(
                [candidate for candidate in resolution.candidates if candidate.can_download and candidate.pdf_url],
                key=lambda item: item.score,
                reverse=True,
            )
            unique_candidates: List[OAPdfCandidate] = []
            seen_urls = set()
            for candidate in downloadable_candidates:
                normalized_url = (candidate.pdf_url or "").strip()
                if not normalized_url or normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                unique_candidates.append(candidate)
            downloadable_candidates = unique_candidates

            if not downloadable_candidates:
                return OAPdfDownloadRecord(
                    pmid=resolution.pmid,
                    doi=resolution.doi,
                    pmcid=resolution.pmcid,
                    source=resolution.best_candidate.source if resolution.best_candidate else "resolver",
                    pdf_url=resolution.best_candidate.pdf_url if resolution.best_candidate else "",
                    status="failed",
                    downloaded_at=self._utc_now(),
                    error=resolution.reason,
                )

            last_error: Optional[str] = None
            for candidate in downloadable_candidates:
                cached_path = None
                if candidate.can_cache:
                    cached_path = self._existing_cached_file(
                        resolution.pmid,
                        resolution.pmcid,
                        resolution.doi,
                    )

                if cached_path and cached_path.exists():
                    return OAPdfDownloadRecord(
                        pmid=resolution.pmid,
                        doi=resolution.doi,
                        pmcid=resolution.pmcid,
                        source=candidate.source,
                        pdf_url=candidate.pdf_url or "",
                        local_path=str(cached_path),
                        filename=cached_path.name,
                        status="downloaded",
                        cached=True,
                        license=candidate.license,
                        downloaded_at=self._utc_now(),
                    )

                try:
                    payload = await self._download_pdf(session, resolution, candidate)
                except Exception as exc:
                    last_error = str(exc) or repr(exc)
                    logger.warning(
                        "OA PDF download failed for %s via %s: %s",
                        resolution.pmid,
                        candidate.source,
                        exc,
                    )
                    continue

                record = OAPdfDownloadRecord(
                    pmid=resolution.pmid,
                    doi=resolution.doi,
                    pmcid=resolution.pmcid,
                    source=candidate.source,
                    pdf_url=candidate.pdf_url or "",
                    local_path=str(payload["path"]),
                    filename=payload["path"].name,
                    status="downloaded",
                    content_type=payload["content_type"],
                    content_length=payload["content_length"],
                    sha256=payload["sha256"],
                    license=candidate.license,
                    cached=False,
                    downloaded_at=self._utc_now(),
                )
                if candidate.can_cache:
                    self._append_manifest(record)
                return record

            first_candidate = downloadable_candidates[0]
            return OAPdfDownloadRecord(
                pmid=resolution.pmid,
                doi=resolution.doi,
                pmcid=resolution.pmcid,
                source=first_candidate.source,
                pdf_url=first_candidate.pdf_url or "",
                status="failed",
                license=first_candidate.license,
                downloaded_at=self._utc_now(),
                error=last_error or "No OA PDF candidate could be downloaded",
            )

    def _build_pmc_fallback_candidate(self, pmcid: str) -> OAPdfCandidate:
        normalized = self._normalize_pmcid(pmcid)
        return OAPdfCandidate(
            source="pmc",
            pdf_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized}/pdf/",
            landing_page_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized}/",
            host_type="repository",
            evidence="PMCID available from PubMed metadata; using PMC article page fallback",
            can_download=True,
            can_cache=True,
            score=70.0 if self.prefer_pmc else 60.0,
        )

    async def _resolve_pmc_candidates(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
    ) -> List[OAPdfCandidate]:
        normalized = self._normalize_pmcid(pmcid)
        params = {"id": normalized}
        async with session.get(PMC_OA_API_URL, params=params, headers=DEFAULT_DOWNLOAD_HEADERS) as response:
            response.raise_for_status()
            xml_text = await response.text()

        root = ElementTree.fromstring(xml_text)
        record = root.find(".//record")
        if record is None:
            return [self._build_pmc_fallback_candidate(normalized)]

        license_value = record.attrib.get("license")
        links = record.findall("./link")
        pdf_candidates: List[OAPdfCandidate] = []
        for link in links:
            link_format = link.attrib.get("format", "").strip().lower()
            href = link.attrib.get("href", "").strip()
            if not href:
                continue
            resource_url = self._normalize_pmc_resource_href(href)
            if link_format == "pdf":
                pdf_candidates.append(
                    OAPdfCandidate(
                        source="pmc",
                        pdf_url=resource_url,
                        landing_page_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized}/",
                        license=license_value,
                        host_type="repository",
                        evidence="PDF resource discovered through the PMC OA Web Service API",
                        can_download=True,
                        can_cache=True,
                        score=140.0 if self.prefer_pmc else 120.0,
                    )
                )
            elif link_format == "tgz":
                pdf_candidates.append(
                    OAPdfCandidate(
                        source="pmc",
                        pdf_url=resource_url,
                        landing_page_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized}/",
                        license=license_value,
                        host_type="repository",
                        evidence="PMC OA Web Service API exposed an article package; PDF extraction will use the package",
                        can_download=True,
                        can_cache=True,
                        score=135.0 if self.prefer_pmc else 115.0,
                    )
                )

        if pdf_candidates:
            return pdf_candidates

        return [
            OAPdfCandidate(
                source="pmc",
                pdf_url=None,
                landing_page_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized}/",
                license=license_value,
                host_type="repository",
                evidence="PMC OA Web Service API reported the article but did not expose a PDF resource",
                can_download=False,
                can_cache=bool(license_value) or not self.cache_only_when_license_known,
                score=20.0,
            )
        ]

    async def _resolve_unpaywall(
        self,
        session: aiohttp.ClientSession,
        doi: str,
    ) -> List[OAPdfCandidate]:
        encoded_doi = quote(doi, safe="")
        url = f"https://api.unpaywall.org/v2/{encoded_doi}?email={quote(self.unpaywall_email or '', safe='@')}"

        async with session.get(url) as response:
            if response.status == 404:
                return []
            response.raise_for_status()
            payload = await response.json()

        if not payload.get("is_oa"):
            return []

        candidates: List[OAPdfCandidate] = []
        locations = []
        best_location = payload.get("best_oa_location")
        if best_location:
            locations.append(best_location)
        locations.extend(payload.get("oa_locations", []))

        seen = set()
        for location in locations:
            pdf_url = location.get("url_for_pdf")
            landing_page_url = location.get("url")
            key = pdf_url or landing_page_url
            if not key or key in seen:
                continue
            seen.add(key)
            license_value = location.get("license")
            host_type = location.get("host_type")
            can_cache = bool(license_value) or not self.cache_only_when_license_known
            score = 80.0
            if pdf_url:
                score += 20.0
            if host_type == "repository":
                score += 5.0
            if license_value:
                score += 3.0
            candidates.append(
                OAPdfCandidate(
                    source="unpaywall",
                    pdf_url=pdf_url,
                    landing_page_url=landing_page_url,
                    license=license_value,
                    host_type=host_type if host_type in {"publisher", "repository"} else None,
                    version=location.get("version"),
                    evidence="Open-access location reported by Unpaywall",
                    can_download=bool(pdf_url),
                    can_cache=can_cache,
                    score=score,
                )
            )

        return candidates

    def _choose_best_candidate(self, candidates: List[OAPdfCandidate]) -> Optional[OAPdfCandidate]:
        downloadable = [candidate for candidate in candidates if candidate.can_download]
        if not downloadable:
            return None
        return max(downloadable, key=lambda candidate: candidate.score)

    async def _download_pdf(
        self,
        session: aiohttp.ClientSession,
        resolution: OAPdfResolution,
        candidate: OAPdfCandidate,
    ) -> Dict[str, Any]:
        if not candidate or not candidate.pdf_url:
            raise ValueError("No downloadable OA PDF candidate is available")

        last_error: Optional[Exception] = None
        for _ in range(self.max_retries):
            try:
                headers = dict(DEFAULT_DOWNLOAD_HEADERS)
                if candidate.landing_page_url:
                    headers["Referer"] = candidate.landing_page_url
                request_timeout: aiohttp.ClientTimeout | None = None
                if candidate.source == "pmc" and candidate.pdf_url and candidate.pdf_url.endswith(".tar.gz"):
                    request_timeout = aiohttp.ClientTimeout(total=max(self.timeout_seconds, 180))
                async with session.get(
                    candidate.pdf_url,
                    allow_redirects=True,
                    headers=headers,
                    timeout=request_timeout,
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    data = await response.read()
                    if candidate.source == "pmc" and candidate.pdf_url and candidate.pdf_url.endswith(".tar.gz"):
                        extracted_pdf = self._extract_pdf_from_pmc_package(data)
                        self._validate_pdf_response(extracted_pdf, "application/pdf")
                        data = extracted_pdf
                        content_type = "application/pdf"
                    else:
                        self._validate_pdf_response(data, content_type)
                    if self._is_pmc_download_challenge(data):
                        raise ValueError(
                            "PMC returned an interactive proof-of-work challenge page instead of a PDF"
                        )

                    path = self._build_output_path(resolution, candidate)
                    path.write_bytes(data)
                    return {
                        "path": path,
                        "content_type": content_type,
                        "content_length": len(data),
                        "sha256": self._calculate_sha256(data),
                    }
            except Exception as exc:
                last_error = exc

        raise last_error or RuntimeError("Unknown OA PDF download failure")

    def _is_pmc_download_challenge(self, data: bytes) -> bool:
        text = data[:4096].decode("utf-8", errors="ignore")
        return "Preparing to download" in text and "POW_CHALLENGE" in text

    def _normalize_pmc_resource_href(self, href: str) -> str:
        if href.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
            return href.replace("ftp://ftp.ncbi.nlm.nih.gov/", "https://ftp.ncbi.nlm.nih.gov/", 1)
        return href

    def _extract_pdf_from_pmc_package(self, archive_data: bytes) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file:
            tmp_file.write(archive_data)
            tmp_path = Path(tmp_file.name)

        try:
            with tarfile.open(tmp_path, mode="r:gz") as archive:
                members = archive.getmembers()
                pdf_members = [
                    member for member in members
                    if member.isfile() and member.name.lower().endswith(".pdf")
                ]
                if not pdf_members:
                    raise ValueError("PMC article package did not contain a PDF file")

                preferred = min(
                    pdf_members,
                    key=lambda member: (
                        "supplement" in member.name.lower() or "appendix" in member.name.lower(),
                        len(member.name),
                    ),
                )
                extracted = archive.extractfile(preferred)
                if extracted is None:
                    raise ValueError("PMC article package PDF could not be extracted")
                return extracted.read()
        finally:
            tmp_path.unlink(missing_ok=True)

    def _build_output_path(self, resolution: OAPdfResolution, candidate: OAPdfCandidate) -> Path:
        filename = self._build_filename(resolution, candidate)
        target_dir = self.cache_dir if candidate.can_cache else self.cache_dir / "_temp"
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / filename

    def _build_filename(self, resolution: OAPdfResolution, candidate: OAPdfCandidate) -> str:
        if resolution.pmcid:
            stem = self._sanitize_filename_component(resolution.pmcid)
        elif resolution.pmid:
            stem = f"PMID_{self._sanitize_filename_component(resolution.pmid)}"
        elif resolution.doi:
            stem = f"DOI_{self._sanitize_filename_component(resolution.doi)}"
        else:
            stem = "article"
        suffix = candidate.source if candidate.can_cache else f"{candidate.source}_temp"
        return f"{stem}_{suffix}.pdf"

    def _existing_cached_file(
        self,
        pmid: Optional[str],
        pmcid: Optional[str],
        doi: Optional[str],
    ) -> Optional[Path]:
        if pmcid:
            matches = list(self.cache_dir.glob(f"{pmcid}_*.pdf"))
            if matches:
                return matches[0]
        if pmid:
            matches = list(self.cache_dir.glob(f"PMID_{pmid}_*.pdf"))
            if matches:
                return matches[0]
        if doi:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", doi)
            matches = list(self.cache_dir.glob(f"DOI_{safe}_*.pdf"))
            if matches:
                return matches[0]
        return None

    def _append_manifest(self, record: OAPdfDownloadRecord) -> None:
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")

    async def _resolve_pdf_from_landing_page(
        self,
        session: aiohttp.ClientSession,
        candidate: OAPdfCandidate,
    ) -> Optional[str]:
        if not candidate.landing_page_url:
            return None

        headers = dict(DEFAULT_DOWNLOAD_HEADERS)
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        async with session.get(candidate.landing_page_url, headers=headers, allow_redirects=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" not in content_type:
                return None
            html = await response.text()

        parser = AnchorCollector()
        parser.feed(html)
        base_url = str(response.url)
        for link in parser.links:
            href = link.get("href", "")
            if not href:
                continue
            score = self._score_anchor_for_pdf(link)
            if score <= 0:
                continue
            full_url = urljoin(base_url, href)
            if self._looks_like_pdf_url(full_url):
                return full_url

        return None

    def _score_anchor_for_pdf(self, link: Dict[str, str]) -> int:
        href = link.get("href", "").lower()
        text = link.get("text", "").lower()
        aria_label = link.get("aria_label", "").lower()
        score = 0
        if href.endswith(".pdf") or ".pdf?" in href:
            score += 5
        if "pdf" in href:
            score += 3
        if re.search(r"\bdownload pdf\b", text):
            score += 4
        elif text == "pdf" or text.startswith("pdf "):
            score += 3
        if aria_label.startswith("pdf"):
            score += 3
        if any(excluded in href for excluded in ("supplement", "appendix", "supporting")):
            score -= 10
        return score

    def _looks_like_pdf_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        return ".pdf" in parsed.path.lower() or "pdf" in parsed.path.lower() or "pdf" in parsed.query.lower()

    def _is_legal_landing_page(self, candidate: OAPdfCandidate) -> bool:
        if not candidate.landing_page_url:
            return False
        parsed = urlparse(candidate.landing_page_url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if self.strict_oa and candidate.host_type not in {"publisher", "repository"}:
            return False
        return True

    def _validate_pdf_response(self, data: bytes, content_type: str) -> None:
        if not data:
            raise ValueError("Downloaded file is empty")
        if len(data) > MAX_PDF_SIZE_BYTES:
            raise ValueError("Downloaded PDF exceeded the maximum allowed size")
        if len(data) < 1024:
            raise ValueError("Downloaded file is too small to be a valid PDF")
        if self._is_pmc_download_challenge(data):
            raise ValueError("PMC returned an interactive proof-of-work challenge page instead of a PDF")
        if "pdf" not in content_type.lower() and not data.startswith(b"%PDF"):
            raise ValueError(f"Resolved URL did not return a PDF (content-type: {content_type})")

    def _calculate_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _sanitize_filename_component(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")[:120] or "article"

    def _normalize_doi(self, doi: Optional[str]) -> Optional[str]:
        if not doi:
            return None
        value = str(doi).strip()
        if value.lower().startswith("https://doi.org/"):
            value = value[16:]
        return value or None

    def _normalize_pmcid(self, pmcid: Optional[str]) -> Optional[str]:
        if not pmcid:
            return None
        value = str(pmcid).strip().upper()
        return value if value.startswith("PMC") else f"PMC{value}"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
