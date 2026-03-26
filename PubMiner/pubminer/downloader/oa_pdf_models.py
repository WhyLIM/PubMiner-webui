"""Pydantic models for legal open-access PDF resolution and downloads."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class OAPdfCandidate(BaseModel):
    """A single OA PDF candidate from a provider."""

    source: Literal["pmc", "unpaywall", "europepmc"]
    pdf_url: Optional[str] = Field(None, description="Direct PDF URL when known")
    landing_page_url: Optional[str] = Field(None, description="Publisher or repository landing page")
    license: Optional[str] = Field(None, description="Normalized license string if available")
    host_type: Optional[Literal["publisher", "repository"]] = Field(
        None, description="Type of host serving the OA copy"
    )
    version: Optional[str] = Field(None, description="Article version, e.g. publishedVersion")
    evidence: str = Field("", description="Human-readable explanation for why this candidate exists")
    can_download: bool = Field(False, description="Whether the candidate includes a usable PDF URL")
    can_cache: bool = Field(False, description="Whether long-term cache is allowed by policy")
    score: float = Field(0.0, description="Selection score; higher wins")


class OAPdfResolution(BaseModel):
    """Resolved OA PDF status for an article."""

    pmid: str = Field(..., description="PubMed ID")
    doi: Optional[str] = Field(None, description="DOI")
    pmcid: Optional[str] = Field(None, description="PMCID")
    availability: Literal["available", "unavailable", "ambiguous"] = Field(
        ..., description="Overall OA PDF availability"
    )
    best_candidate: Optional[OAPdfCandidate] = Field(None, description="Preferred candidate if any")
    candidates: List[OAPdfCandidate] = Field(default_factory=list, description="All discovered candidates")
    reason: str = Field("", description="Explanation for the availability result")
    resolved_at: str = Field(..., description="UTC ISO timestamp for the resolution")


class OAPdfDownloadRecord(BaseModel):
    """Result of an attempted OA PDF download."""

    pmid: str = Field(..., description="PubMed ID")
    doi: Optional[str] = Field(None, description="DOI")
    pmcid: Optional[str] = Field(None, description="PMCID")
    source: str = Field(..., description="Provider used for the download")
    pdf_url: str = Field(..., description="Resolved PDF URL used for the download")
    local_path: Optional[str] = Field(None, description="Saved local path")
    filename: Optional[str] = Field(None, description="Saved filename")
    status: Literal["downloaded", "skipped", "failed"] = Field(..., description="Outcome")
    content_type: Optional[str] = Field(None, description="Content-Type returned by server")
    content_length: Optional[int] = Field(None, description="Downloaded bytes")
    sha256: Optional[str] = Field(None, description="SHA-256 hash of downloaded file")
    license: Optional[str] = Field(None, description="License recorded alongside the file")
    cached: bool = Field(False, description="Whether the file was served from cache")
    elapsed_ms: Optional[int] = Field(None, description="Elapsed milliseconds spent resolving/downloading this record")
    downloaded_at: str = Field(..., description="UTC ISO timestamp")
    error: Optional[str] = Field(None, description="Failure reason if any")
