"""
Column mapping configuration for CSV output.

Defines standardized English column names for output.
"""

from typing import Dict, List

# Full mapping: internal names -> standardized English column headers
COLUMN_MAPPING: Dict[str, str] = {
    # Metadata fields
    "pmid": "pmid",
    "pmcid": "pmcid",
    "doi": "doi",
    "title": "title",
    "authors": "authors",
    "first_author": "first_author",
    "affiliation": "affiliation",
    "journal": "journal",
    "journal_abbrev": "j_abbrev",
    "issn": "issn",
    "journal_id": "journal_id",
    "pub_date": "pub_date",
    "year": "year",
    "volume": "volume",
    "issue": "issue",
    "pages": "pages",
    "publication_status": "publication_status",
    "article_type": "article_type",
    "abstract": "abstract",
    "keywords": "keywords",
    "mesh_terms": "mesh_terms",
    "language": "language",
    "status": "status",
    "last_revision_date": "last_revision",
    "grant_list": "grant_list",
    "has_pmc_fulltext": "has_fulltext",
    "cited_count": "cited_count",
    "cited_by": "cited_by",
    "references_count": "references_count",
    "references": "references",
    # Research Background
    "rationale": "rationale",  # 研究动因
    "framework": "framework",  # 理论框架
    "lit_gaps": "lit_gaps",  # 现有研究不足
    "objectives": "objectives",  # 研究目标
    "hypotheses": "hypotheses",  # 研究假设
    # Study Methods
    "sample_n": "sample_n",  # 样本量
    "region": "region",  # 研究区域
    "conditions": "conditions",  # 实验条件
    "data_source": "data_source",  # 数据来源
    "methods": "methods",  # 方法工具
    # Variable Definitions
    "iv": "iv",  # 自变量
    "dv": "dv",  # 因变量
    "cv": "cv",  # 控制变量
    # Research Results
    "findings": "findings",  # 核心发现
    "stats_conclusion": "stats_concl",  # 统计结论
    "hyp_evidence": "hyp_evidence",  # 假设证据
    "interpretation": "interpretation",  # 结果解释
    # Discussion
    "comparison": "vs_prior",  # 与前人比较
    "theory_value": "theory_value",  # 理论意义
    "practical_value": "practical_val",  # 实践价值
    "future_work": "future_work",  # 未来方向
    # Limitations
    "data_limit": "data_limit",  # 数据局限
    "method_limit": "method_limit",  # 方法局限
    "validity_limit": "validity",  # 效度局限
    # Custom fields (aging biomarker example)
    "biomarker_name": "biomarker",
    "biomarker_type": "marker_type",
    "biomarker_category": "marker_cat",
    "population_ethnicity": "ethnicity",
    "gender_ratio": "gender_ratio",
    "biomarker_desc": "marker_desc",
    "measurement_method": "measure_method",
    "validation_status": "validation",
    # Error tracking
    "error": "error",
    "raw_response": "raw_response",
}

# Column order for CSV output
COLUMN_ORDER: List[str] = [
    # === METADATA SECTION (First) ===
    # ID and basic metadata
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
    # Publication details
    "has_fulltext",
    "cited_count",
    "cited_by",
    "references_count",
    "references",
    "grant_list",
    "abstract",
    "keywords",
    "mesh_terms",

    # === LLM EXTRACTION SECTION ===
    # Research Background
    "rationale",
    "framework",
    "lit_gaps",
    "objectives",
    "hypotheses",
    # Study Methods
    "sample_n",
    "region",
    "conditions",
    "data_source",
    "methods",
    # Variables
    "iv",
    "dv",
    "cv",
    # Results
    "findings",
    "stats_concl",
    "hyp_evidence",
    "interpretation",
    # Discussion
    "vs_prior",
    "theory_value",
    "practical_val",
    "future_work",
    # Limitations
    "data_limit",
    "method_limit",
    "validity",

    # === CUSTOM FIELDS SECTION (will be inserted dynamically) ===
    # biomarker, marker_type, marker_cat, etc.

    # === ERROR INFO (Last) ===
    "error",
]


def get_ordered_columns(
    available_columns: List[str],
    custom_columns: List[str] = None,
) -> List[str]:
    """
    Get columns in the correct order for output.

    Args:
        available_columns: Columns that exist in the data
        custom_columns: Additional custom columns to insert

    Returns:
        Ordered list of columns
    """
    ordered = []
    custom_cols = custom_columns or []

    for col in COLUMN_ORDER:
        # Check if column exists (either original name or mapped name)
        if col in available_columns:
            ordered.append(col)
        else:
            # Check for unmapped version
            for orig, mapped in COLUMN_MAPPING.items():
                if mapped == col and orig in available_columns:
                    ordered.append(orig)
                    break

    # Add custom columns after LLM extraction fields
    for custom_col in custom_cols:
        if custom_col not in ordered and custom_col in available_columns:
            # Insert after 'validity' (last LLM field) if possible
            if "validity" in ordered:
                idx = ordered.index("validity")
                ordered.insert(idx + 1, custom_col)
            else:
                ordered.append(custom_col)

    # Add any remaining columns not in order
    for col in available_columns:
        if col not in ordered:
            ordered.append(col)

    return ordered
