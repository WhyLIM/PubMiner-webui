"""Pydantic models for literature metadata."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date
import re


class LiteratureMetadata(BaseModel):
    """
    Literature metadata model.

    Contains all bibliographic information retrieved from PubMed.
    """

    # Basic identifiers
    pmid: str = Field(..., description="PubMed ID")
    pmcid: Optional[str] = Field(None, description="PMC ID (if available)")
    doi: Optional[str] = Field(None, description="Digital Object Identifier")

    # Title and authors
    title: str = Field(..., description="Article title")
    authors: List[str] = Field(default_factory=list, description="Author list")
    first_author: str = Field("", description="First author full name")
    affiliation: str = Field("", description="Author affiliation")

    # Journal information
    journal: str = Field("", description="Journal name")
    journal_abbrev: str = Field("", description="Journal abbreviation")
    issn: str = Field("", description="ISSN")
    journal_id: str = Field("", description="Journal ID")

    # Publication details
    pub_date: Optional[str] = Field(None, description="Publication date")
    year: Optional[int] = Field(None, description="Publication year")
    volume: str = Field("", description="Journal volume")
    issue: str = Field("", description="Journal issue")
    pages: str = Field("", description="Page range")
    publication_status: str = Field("", description="Publication status")
    article_type: str = Field("", description="Article type")

    # Content
    abstract: str = Field("", description="Article abstract")
    keywords: List[str] = Field(default_factory=list, description="Author keywords")
    mesh_terms: List[str] = Field(default_factory=list, description="MeSH terms")
    language: str = Field("", description="Article language")

    # Citation information
    cited_count: int = Field(0, description="Number of times cited")
    cited_by: List[str] = Field(default_factory=list, description="PMIDs of citing articles")
    references_count: int = Field(0, description="Number of references")
    references: List[str] = Field(default_factory=list, description="PMIDs of referenced articles")

    # Additional metadata
    status: str = Field("", description="Article status")
    last_revision_date: str = Field("", description="Last revision date")
    grant_list: str = Field("", description="Grant information")

    # Full-text availability flags
    has_pmc_fulltext: bool = Field(False, description="Has PMC full text")

    @field_validator("pmid")
    @classmethod
    def validate_pmid(cls, v):
        """Validate PMID format."""
        if not re.match(r"^\d+$", str(v)):
            raise ValueError(f"Invalid PMID format: {v}")
        return str(v)

    @field_validator("pmcid")
    @classmethod
    def validate_pmcid(cls, v):
        """Validate PMCID format."""
        if v and not re.match(r"^PMC\d+$", str(v)):
            raise ValueError(f"Invalid PMCID format: {v}")
        return v

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v):
        """Basic DOI validation."""
        if v and not v.startswith("10."):
            # Try to fix common DOI formats
            if "/" in v:
                return f"10.{v}" if not v.startswith("10.") else v
        return v

    def get_author_string(self, max_authors: int = 3) -> str:
        """Get formatted author string with et al. if needed."""
        if not self.authors:
            return ""

        if len(self.authors) <= max_authors:
            return ", ".join(self.authors)
        else:
            return ", ".join(self.authors[:max_authors]) + " et al."

    def get_citation(self) -> str:
        """Generate a citation string."""
        parts = []

        if self.authors:
            parts.append(self.get_author_string())

        parts.append(self.title)

        if self.journal:
            journal_part = self.journal_abbrev or self.journal
            if self.year:
                journal_part += f" {self.year}"
            if self.volume:
                journal_part += f";{self.volume}"
            if self.pages:
                journal_part += f":{self.pages}"
            parts.append(journal_part)

        return ". ".join(parts) + "."

    class Config:
        json_schema_extra = {
            "example": {
                "pmid": "12345678",
                "pmcid": "PMC1234567",
                "doi": "10.1234/example.2024",
                "title": "Example Article Title",
                "authors": ["Smith J", "Doe A", "Johnson B"],
                "journal": "Nature Medicine",
                "year": 2024,
                "abstract": "This is an example abstract...",
            }
        }
