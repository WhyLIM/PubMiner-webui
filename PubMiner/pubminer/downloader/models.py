"""Pydantic models for full-text documents."""

from pydantic import BaseModel, Field
from typing import Dict, Optional, Union, List
from enum import Enum


class FullTextDocument(BaseModel):
    """
    Full-text document model.

    Contains both raw and processed full-text content.
    """

    pmid: str = Field(..., description="PubMed ID")
    pmcid: str = Field(..., description="PMC ID")
    raw_bioc: Optional[Union[Dict, List]] = Field(None, description="Raw BioC JSON data")
    filtered_text: str = Field("", description="Filtered text for LLM extraction")
    sections: Dict[str, str] = Field(default_factory=dict, description="Text by section type")
    title: str = Field("", description="Article title")

    # Metadata
    total_chars: int = Field(0, description="Total characters in filtered text")
    total_tokens_estimate: int = Field(0, description="Estimated token count")

    def get_section_text(self, section_type: str) -> str:
        """Get text for a specific section type."""
        return self.sections.get(section_type.upper(), "")

    def estimate_tokens(self, chars_per_token: float = 4.0) -> int:
        """Estimate token count for the text."""
        self.total_chars = len(self.filtered_text)
        self.total_tokens_estimate = int(self.total_chars / chars_per_token)
        return self.total_tokens_estimate

    class Config:
        arbitrary_types_allowed = True
