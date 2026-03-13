"""Extractor module: LLM-based structured information extraction."""

from pubminer.extractor.zhipu_client import ZhipuExtractor
from pubminer.extractor.schemas.base_info import BaseExtractionModel
from pubminer.extractor.schemas.custom import (
    CustomFieldDefinition,
    DynamicSchemaBuilder,
    AGING_BIOMARKER_FIELDS,
)

__all__ = [
    "ZhipuExtractor",
    "BaseExtractionModel",
    "CustomFieldDefinition",
    "DynamicSchemaBuilder",
    "AGING_BIOMARKER_FIELDS",
]
