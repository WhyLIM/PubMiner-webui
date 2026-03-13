"""
Section parser for BioC documents.

Filters and categorizes text sections by type.
"""

from enum import Enum
from typing import Dict, List, Optional
import re

from pubminer.core.logger import get_logger

logger = get_logger("downloader")


class SectionType(Enum):
    """
    Literature section types.

    Ordered roughly by typical article structure.
    """

    ABSTRACT = "ABSTRACT"
    INTRODUCTION = "INTRO"
    METHODS = "METHODS"
    RESULTS = "RESULTS"
    DISCUSSION = "DISCUSSION"
    CONCLUSION = "CONCLUSION"
    REFERENCES = "REFERENCES"
    ACKNOWLEDGMENTS = "ACK"
    SUPPLEMENT = "SUPPL"
    OTHER = "OTHER"


# Section title mapping for different journal conventions
SECTION_TITLE_MAP = {
    # Abstract variations
    "abstract": SectionType.ABSTRACT,
    "summary": SectionType.ABSTRACT,
    "background abstract": SectionType.ABSTRACT,
    "author summary": SectionType.ABSTRACT,
    "structured abstract": SectionType.ABSTRACT,
    "plain language summary": SectionType.ABSTRACT,
    # Introduction variations
    "introduction": SectionType.INTRODUCTION,
    "background": SectionType.INTRODUCTION,
    "background and objectives": SectionType.INTRODUCTION,
    "objectives": SectionType.INTRODUCTION,
    "introduction and background": SectionType.INTRODUCTION,
    "research in context": SectionType.INTRODUCTION,
    "overview": SectionType.INTRODUCTION,
    # Methods variations
    "methods": SectionType.METHODS,
    "methodology": SectionType.METHODS,
    "materials and methods": SectionType.METHODS,
    "materials & methods": SectionType.METHODS,
    "patients and methods": SectionType.METHODS,
    "study design and methods": SectionType.METHODS,
    "experimental procedures": SectionType.METHODS,
    "study population": SectionType.METHODS,
    "participants": SectionType.METHODS,
    "data and methods": SectionType.METHODS,
    "method": SectionType.METHODS,
    "statistical analysis": SectionType.METHODS,
    "statistical methods": SectionType.METHODS,
    # Results variations
    "results": SectionType.RESULTS,
    "findings": SectionType.RESULTS,
    "outcomes": SectionType.RESULTS,
    "main results": SectionType.RESULTS,
    "key results": SectionType.RESULTS,
    "observations": SectionType.RESULTS,
    # Discussion variations
    "discussion": SectionType.DISCUSSION,
    "comments": SectionType.DISCUSSION,
    "interpretation": SectionType.DISCUSSION,
    "discussion and conclusion": SectionType.DISCUSSION,
    "general discussion": SectionType.DISCUSSION,
    # Conclusion variations
    "conclusion": SectionType.CONCLUSION,
    "conclusions": SectionType.CONCLUSION,
    "concluding remarks": SectionType.CONCLUSION,
    "final remarks": SectionType.CONCLUSION,
    "conclusion and future directions": SectionType.CONCLUSION,
    "key messages": SectionType.CONCLUSION,
    # References
    "references": SectionType.REFERENCES,
    "bibliography": SectionType.REFERENCES,
    "literature cited": SectionType.REFERENCES,
    "notes": SectionType.REFERENCES,
    # Acknowledgments
    "acknowledgments": SectionType.ACKNOWLEDGMENTS,
    "acknowledgements": SectionType.ACKNOWLEDGMENTS,
    "funding": SectionType.ACKNOWLEDGMENTS,
    "author contributions": SectionType.ACKNOWLEDGMENTS,
    "competing interests": SectionType.ACKNOWLEDGMENTS,
    "conflict of interest": SectionType.ACKNOWLEDGMENTS,
    "ethics statement": SectionType.ACKNOWLEDGMENTS,
    # Supplementary
    "supplementary": SectionType.SUPPLEMENT,
    "supplementary material": SectionType.SUPPLEMENT,
    "supplementary data": SectionType.SUPPLEMENT,
    "appendix": SectionType.SUPPLEMENT,
    "supporting information": SectionType.SUPPLEMENT,
}

# Default sections to keep for LLM extraction
DEFAULT_KEEP_SECTIONS = [
    SectionType.ABSTRACT,
    SectionType.INTRODUCTION,
    SectionType.METHODS,
    SectionType.RESULTS,
    SectionType.DISCUSSION,
    SectionType.CONCLUSION,
]


class BioCSectionParser:
    """
    Parser for BioC document sections.

    Extracts, classifies, and filters text sections from BioC format.
    """

    def __init__(
        self,
        keep_sections: Optional[List[SectionType]] = None,
        min_section_length: int = 50,
    ):
        """
        Initialize the section parser.

        Args:
            keep_sections: List of section types to keep (default: research content)
            min_section_length: Minimum characters for a section to be included
        """
        self.keep_sections = keep_sections or DEFAULT_KEEP_SECTIONS
        self.min_section_length = min_section_length

    def _normalize_heading(self, text: str) -> str:
        """Normalize section headings before matching."""
        normalized = text.lower().strip()
        normalized = re.sub(r"^[\d\W_]+", "", normalized)
        normalized = re.sub(r"[\d\W_]+$", "", normalized)
        normalized = normalized.replace("&", " and ")
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"^(section|sec)\s+\d+[:.]?\s*", "", normalized)
        normalized = re.sub(r"^\d+(\.\d+)*\s+", "", normalized)
        return normalized.strip(" :.-")

    def parse_bioc_document(self, bioc_data: Dict) -> Dict[SectionType, str]:
        """
        Parse a BioC document and categorize sections.

        Args:
            bioc_data: BioC JSON data (can be a list or dict)

        Returns:
            Dictionary mapping section types to text
        """
        sections: Dict[SectionType, str] = {}

        if not bioc_data:
            return sections

        # Handle BioC response format (list containing collection)
        if isinstance(bioc_data, list):
            if not bioc_data:
                return sections
            bioc_data = bioc_data[0]

        # Get passages from document
        documents = bioc_data.get("documents", [])
        if not documents:
            return sections

        passages = documents[0].get("passages", [])

        for passage in passages:
            section_type = self._classify_section(passage)
            text = passage.get("text", "").strip()

            # Skip short sections
            if len(text) < self.min_section_length:
                continue

            # Accumulate text by section type
            if section_type in sections:
                sections[section_type] += "\n\n" + text
            else:
                sections[section_type] = text

        return sections

    def _classify_section(self, passage: Dict) -> SectionType:
        """
        Classify a passage into a section type.

        Uses multiple heuristics:
        1. BioC infons.section_type
        2. Passage heading/title
        3. Content patterns
        """
        infons = passage.get("infons", {})

        # Method 1: Check multiple BioC heading/section infons
        heading_candidates = [
            infons.get("section_type", ""),
            infons.get("type", ""),
            infons.get("section", ""),
            infons.get("title", ""),
            infons.get("heading", ""),
            infons.get("subtitle", ""),
            infons.get("label", ""),
        ]
        for candidate in heading_candidates:
            if not candidate:
                continue
            section_type = self._match_section_type(str(candidate))
            if section_type != SectionType.OTHER:
                return section_type

        # Method 2: infer from body type-like hints
        passage_type = str(infons.get("type", "")).lower()
        if passage_type in {"abstract", "title_abstract"}:
            return SectionType.ABSTRACT

        # Method 3: infer from content
        section_type = self._infer_from_content(passage.get("text", ""))
        if section_type != SectionType.OTHER:
            return section_type

        return SectionType.OTHER

    def _match_section_type(self, text: str) -> SectionType:
        """Match section type from text using the mapping."""
        text_lower = self._normalize_heading(text)

        # Direct match
        if text_lower in SECTION_TITLE_MAP:
            return SECTION_TITLE_MAP[text_lower]

        # Partial match (for variations)
        for key, section_type in SECTION_TITLE_MAP.items():
            if key in text_lower or text_lower in key:
                return section_type

        if any(term in text_lower for term in ["method", "materials", "participant", "protocol"]):
            return SectionType.METHODS
        if any(term in text_lower for term in ["result", "finding", "outcome", "observation"]):
            return SectionType.RESULTS
        if any(term in text_lower for term in ["discussion", "interpretation", "implication"]):
            return SectionType.DISCUSSION
        if any(term in text_lower for term in ["conclusion", "concluding", "summary"]):
            return SectionType.CONCLUSION
        if any(term in text_lower for term in ["reference", "bibliography", "works cited"]):
            return SectionType.REFERENCES

        # Check if it's a reference pattern
        if re.match(r"^\d+\.", text_lower) or "et al" in text_lower[:100]:
            return SectionType.REFERENCES

        return SectionType.OTHER

    def _infer_from_content(self, text: str) -> SectionType:
        """Infer section type from content patterns."""
        text_lower = text.lower()[:500]  # Check first 500 chars

        # Method indicators
        method_patterns = [
            "we used",
            "we performed",
            "was measured",
            "statistical analysis",
            "participants were",
            "study design",
            "inclusion criteria",
            "data collection",
            "retrospective cohort",
            "prospective cohort",
            "randomized",
            "cross-sectional",
            "logistic regression",
            "multivariable",
        ]

        # Result indicators
        result_patterns = [
            "we found",
            "results showed",
            "significantly",
            "p <",
            "p=",
            "table 1",
            "figure 1",
            "odds ratio",
            "hazard ratio",
            "confidence interval",
            "was associated with",
        ]

        # Discussion indicators
        discussion_patterns = [
            "our findings",
            "this study",
            "previous studies",
            "consistent with",
            "in contrast to",
            "limitations",
            "these findings suggest",
            "in summary",
            "the present study",
        ]

        introduction_patterns = [
            "little is known",
            "remains unclear",
            "we aimed to",
            "the purpose of this study",
            "the aim of this study",
            "background",
        ]

        conclusion_patterns = [
            "in conclusion",
            "we conclude",
            "our results suggest",
            "taken together",
            "future studies",
        ]

        # Count matches
        intro_score = sum(1 for p in introduction_patterns if p in text_lower)
        method_score = sum(1 for p in method_patterns if p in text_lower)
        result_score = sum(1 for p in result_patterns if p in text_lower)
        discussion_score = sum(1 for p in discussion_patterns if p in text_lower)
        conclusion_score = sum(1 for p in conclusion_patterns if p in text_lower)

        scores = {
            SectionType.INTRODUCTION: intro_score,
            SectionType.METHODS: method_score,
            SectionType.RESULTS: result_score,
            SectionType.DISCUSSION: discussion_score,
            SectionType.CONCLUSION: conclusion_score,
        }
        max_score = max(scores.values())

        if max_score == 0:
            return SectionType.OTHER

        return next(section for section, score in scores.items() if score == max_score)

    def get_filtered_text(
        self,
        bioc_data: Dict,
        include_section_headers: bool = True,
    ) -> str:
        """
        Get filtered text for LLM extraction.

        Only includes sections in keep_sections list.

        Args:
            bioc_data: BioC JSON data
            include_section_headers: Include [SECTION_TYPE] headers

        Returns:
            Filtered text string
        """
        sections = self.parse_bioc_document(bioc_data)

        # Order sections by typical article structure
        section_order = [
            SectionType.ABSTRACT,
            SectionType.INTRODUCTION,
            SectionType.METHODS,
            SectionType.RESULTS,
            SectionType.DISCUSSION,
            SectionType.CONCLUSION,
        ]

        parts = []
        for section_type in section_order:
            if section_type in self.keep_sections and section_type in sections:
                text = sections[section_type].strip()
                if text:
                    if include_section_headers:
                        parts.append(f"[{section_type.value}]\n{text}")
                    else:
                        parts.append(text)

        return "\n\n".join(parts)

    def get_fallback_text(
        self,
        bioc_data: Dict,
        include_section_headers: bool = True,
    ) -> str:
        """
        Build a best-effort full text when standard section parsing fails.

        This keeps article body content even when BioC section metadata is
        missing or non-standard, while still filtering obvious non-body text
        such as references and acknowledgments when possible.
        """
        passages = self._get_passages(bioc_data)
        if not passages:
            return ""

        parts: List[str] = []
        for passage in passages:
            text = passage.get("text", "").strip()
            if len(text) < self.min_section_length:
                continue

            section_type = self._classify_section(passage)
            if section_type in {
                SectionType.REFERENCES,
                SectionType.ACKNOWLEDGMENTS,
                SectionType.SUPPLEMENT,
            }:
                continue

            if include_section_headers and section_type != SectionType.OTHER:
                parts.append(f"[{section_type.value}]\n{text}")
            else:
                parts.append(text)

        return "\n\n".join(parts)

    def _get_passages(self, bioc_data: Dict) -> List[Dict]:
        """Return document passages from a BioC payload."""
        if not bioc_data:
            return []

        if isinstance(bioc_data, list):
            if not bioc_data:
                return []
            bioc_data = bioc_data[0]

        documents = bioc_data.get("documents", [])
        if not documents:
            return []

        return documents[0].get("passages", [])

    def get_section_summary(self, bioc_data: Dict) -> Dict[str, int]:
        """Get a summary of sections and their character counts."""
        sections = self.parse_bioc_document(bioc_data)

        return {
            section_type.value: len(text)
            for section_type, text in sections.items()
        }
