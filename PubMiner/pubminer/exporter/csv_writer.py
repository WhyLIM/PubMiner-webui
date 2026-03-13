"""
CSV exporter for extraction results.

Merges metadata and extraction results into standardized CSV output.
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from pubminer.core.logger import get_logger
from pubminer.exporter.column_mapping import COLUMN_MAPPING, get_ordered_columns

logger = get_logger("exporter")


class CSVExporter:
    """
    CSV exporter for literature extraction results.

    Merges metadata with extraction results and exports to a
    standardized CSV format with proper column ordering.
    """

    def __init__(
        self,
        custom_columns: Optional[List[str]] = None,
    ):
        """
        Initialize the CSV exporter.

        Args:
            custom_columns: List of custom column names to include
        """
        self.custom_columns = custom_columns or []

    def export(
        self,
        metadata_list: List[Dict],
        extraction_results: List[Dict],
        output_path: str,
        include_abstract: bool = False,
        include_keywords: bool = True,
        include_citations: bool = True,
    ) -> str:
        """
        Export metadata and extraction results to CSV.

        Args:
            metadata_list: List of literature metadata dictionaries
            extraction_results: List of extraction result dictionaries
            output_path: Output file path
            include_abstract: Whether to include abstract in output
            include_keywords: Whether to include keywords in output
            include_citations: Whether to include citation-related columns

        Returns:
            Path to the created CSV file
        """
        # Build data map indexed by PMID
        data_map: Dict[str, Dict] = {}

        # Add metadata
        for meta in metadata_list:
            # Handle both Pydantic model and dict
            if hasattr(meta, 'model_dump'):
                meta_dict = meta.model_dump()
            elif hasattr(meta, 'dict'):
                meta_dict = meta.dict()
            else:
                meta_dict = meta

            pmid = str(meta_dict.get("pmid", ""))
            if pmid:
                data_map[pmid] = {"pmid": pmid}
                # Flatten list fields
                for key, value in meta_dict.items():
                    if isinstance(value, list):
                        data_map[pmid][key] = "; ".join(str(v) for v in value)
                    else:
                        data_map[pmid][key] = value

        # Add extraction results
        for result in extraction_results:
            pmid = str(result.get("pmid", ""))
            if pmid in data_map:
                # Merge extraction results
                for key, value in result.items():
                    if key != "pmid":
                        data_map[pmid][key] = value
            elif pmid:
                # PMID not in metadata (shouldn't happen normally)
                data_map[pmid] = {"pmid": pmid}
                for key, value in result.items():
                    data_map[pmid][key] = value

        if not data_map:
            logger.warning("No data to export")
            return ""

        # Convert to DataFrame
        df = pd.DataFrame(list(data_map.values()))

        # Rename columns to standardized names
        df = df.rename(columns=COLUMN_MAPPING)

        # Get ordered columns
        available_cols = list(df.columns)
        ordered_cols = get_ordered_columns(available_cols, self.custom_columns)

        # Filter to only existing columns
        ordered_cols = [col for col in ordered_cols if col in df.columns]

        # Optionally drop abstract
        if not include_abstract and "abstract" in ordered_cols:
            ordered_cols.remove("abstract")

        # Optionally drop keywords
        if not include_keywords and "keywords" in ordered_cols:
            ordered_cols.remove("keywords")

        # Optionally drop citation columns
        if not include_citations:
            ordered_cols = [
                col for col in ordered_cols
                if col not in {"cited_count", "references_count", "cited_by", "references"}
            ]

        # Reorder DataFrame
        df = df[ordered_cols]

        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Export to CSV with UTF-8 BOM for Excel compatibility
        df.to_csv(output_file, index=False, encoding="utf-8-sig")

        logger.info(f"Exported {len(df)} records to {output_file}")

        return str(output_file)

    def export_metadata_only(
        self,
        metadata_list: List[Dict],
        output_path: str,
    ) -> str:
        """
        Export only metadata (before extraction).

        Useful for reviewing retrieved articles before processing.

        Args:
            metadata_list: List of literature metadata dictionaries
            output_path: Output file path

        Returns:
            Path to the created CSV file
        """
        # Flatten list fields
        flat_data = []
        for meta in metadata_list:
            flat = {}
            for key, value in meta.items():
                if isinstance(value, list):
                    flat[key] = "; ".join(str(v) for v in value)
                else:
                    flat[key] = value
            flat_data.append(flat)

        df = pd.DataFrame(flat_data)

        # Rename and order columns
        df = df.rename(columns=COLUMN_MAPPING)

        # Basic column order for metadata only
        meta_order = [
            "pmid",
            "pmcid",
            "doi",
            "title",
            "authors",
            "first_author",
            "affiliation",
            "journal",
            "j_abbrev",
            "issn",
            "journal_id",
            "pub_date",
            "year",
            "volume",
            "issue",
            "pages",
            "article_type",
            "publication_status",
            "language",
            "status",
            "last_revision",
            "has_fulltext",
            "cited_count",
            "references_count",
            "grant_list",
            "abstract",
            "keywords",
            "mesh_terms",
        ]

        ordered = [col for col in meta_order if col in df.columns]
        # Add remaining columns
        for col in df.columns:
            if col not in ordered:
                ordered.append(col)

        df = df[ordered]

        # Export
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_file, index=False, encoding="utf-8-sig")

        logger.info(f"Exported {len(df)} metadata records to {output_file}")

        return str(output_file)

    @staticmethod
    def generate_output_filename(
        prefix: str = "pubminer_result",
        suffix: str = "",
        timestamp: bool = True,
    ) -> str:
        """
        Generate a timestamped output filename.

        Args:
            prefix: Filename prefix
            suffix: Filename suffix
            timestamp: Whether to include timestamp

        Returns:
            Generated filename
        """
        parts = [prefix]

        if timestamp:
            parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))

        if suffix:
            parts.append(suffix)

        return "_".join(parts) + ".csv"
