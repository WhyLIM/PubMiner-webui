"""
Dynamic schema builder for custom extraction fields.

Allows users to define custom fields for domain-specific extraction.
"""

from pydantic import BaseModel, Field, create_model
from typing import Type, List, Optional, Any
from enum import Enum
import yaml
from pathlib import Path

from pubminer.core.logger import get_logger
from pubminer.extractor.schemas.base_info import BaseExtractionModel

logger = get_logger("extractor")


class CustomFieldDefinition(BaseModel):
    """
    Definition of a custom extraction field.

    Used to dynamically create Pydantic models with custom fields.
    """

    name: str = Field(..., description="Field name (English, used as column header)")
    description: str = Field(..., description="Field description for LLM prompt")
    field_type: str = Field("str", description="Field type: str, int, float, enum")
    enum_values: List[str] = Field(default_factory=list, description="Enum values if field_type='enum'")
    required: bool = Field(False, description="Whether field is required")
    default: Any = Field("", description="Default value")

    def get_python_type(self) -> Type:
        """Get the Python type for this field."""
        if self.field_type == "int":
            return int
        elif self.field_type == "float":
            return float
        elif self.field_type == "enum" and self.enum_values:
            # Create enum dynamically
            enum_name = f"{self.name.title().replace('_', '')}Enum"
            return Enum(enum_name, {v.upper(): v for v in self.enum_values})
        else:
            return str


class DynamicSchemaBuilder:
    """
    Builder for creating dynamic Pydantic models with custom fields.

    Enables runtime extension of extraction schemas without code changes.
    """

    @staticmethod
    def create_custom_model(
        base_model: Type[BaseModel] = BaseExtractionModel,
        custom_fields: List[CustomFieldDefinition] = None,
        model_name: str = "CustomExtractionModel",
    ) -> Type[BaseModel]:
        """
        Create a custom extraction model by extending the base model.

        Args:
            base_model: Base Pydantic model to extend
            custom_fields: List of custom field definitions
            model_name: Name for the generated model

        Returns:
            New Pydantic model class with custom fields
        """
        if not custom_fields:
            return base_model

        # Build field definitions
        field_definitions = {}

        for cf in custom_fields:
            try:
                field_type = cf.get_python_type()

                # Handle enum types
                if cf.field_type == "enum" and cf.enum_values:
                    # For enum, we'll use string type but document the enum values in description
                    field_definitions[cf.name] = (
                        str,
                        Field(
                            default=cf.default,
                            description=f"{cf.description} (可选值: {', '.join(cf.enum_values)})",
                        ),
                    )
                else:
                    field_definitions[cf.name] = (
                        field_type,
                        Field(default=cf.default, description=cf.description),
                    )

            except Exception as e:
                logger.warning(f"Failed to create field {cf.name}: {e}")
                continue

        # Create the model
        if field_definitions:
            return create_model(
                model_name,
                __base__=base_model,
                **field_definitions,
            )

        return base_model

    @staticmethod
    def from_yaml(yaml_path: str) -> Type[BaseModel]:
        """
        Load custom fields from YAML and create a model.

        Args:
            yaml_path: Path to custom fields YAML file

        Returns:
            Custom Pydantic model
        """
        path = Path(yaml_path)
        if not path.exists():
            logger.warning(f"Custom fields file not found: {yaml_path}")
            return BaseExtractionModel

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        fields_data = data.get("fields", [])
        custom_fields = [CustomFieldDefinition(**fd) for fd in fields_data]

        additional_instructions = data.get("additional_instructions", "")

        model = DynamicSchemaBuilder.create_custom_model(
            custom_fields=custom_fields,
        )

        # Attach additional instructions to the model
        model._additional_instructions = additional_instructions

        return model


# Predefined custom fields for aging biomarker research
AGING_BIOMARKER_FIELDS = [
    CustomFieldDefinition(
        name="biomarker_name",
        description="文章中研究的生物标志物名称",
        field_type="str",
    ),
    CustomFieldDefinition(
        name="biomarker_type",
        description="属于单个生物标志物还是组合生物标志物",
        field_type="enum",
        enum_values=["Single", "Composite", "Panel", "Unknown"],
    ),
    CustomFieldDefinition(
        name="biomarker_category",
        description="生物标志物的分子分类",
        field_type="enum",
        enum_values=["Protein", "DNA", "RNA", "Metabolite", "Epigenetic", "Cellular", "Other"],
    ),
    CustomFieldDefinition(
        name="population_ethnicity",
        description="研究样本人群的种族/族裔",
        field_type="str",
    ),
    CustomFieldDefinition(
        name="gender_ratio",
        description="研究样本的男女比例（如 'Male: 45%, Female: 55%'）",
        field_type="str",
    ),
    CustomFieldDefinition(
        name="biomarker_desc",
        description="关于该生物标志物的具体描述和研究发现",
        field_type="str",
    ),
    CustomFieldDefinition(
        name="measurement_method",
        description="生物标志物的测量方法（如ELISA、qPCR等）",
        field_type="str",
    ),
    CustomFieldDefinition(
        name="validation_status",
        description="是否经过独立队列验证",
        field_type="enum",
        enum_values=["Validated", "Not validated", "Partially validated"],
    ),
]


def get_aging_biomarker_model() -> Type[BaseModel]:
    """Get the aging biomarker extraction model."""
    return DynamicSchemaBuilder.create_custom_model(
        custom_fields=AGING_BIOMARKER_FIELDS,
        model_name="AgingBiomarkerExtractionModel",
    )
