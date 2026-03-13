"""Global configuration management using Pydantic Settings."""

import os
import re
from pathlib import Path
from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class NCBIConfig(BaseSettings):
    """NCBI API configuration."""

    email: str = Field(..., description="Email address required by NCBI")
    api_key: Optional[str] = Field(None, description="NCBI API key for higher rate limits")
    tool_name: str = Field("PubMiner", description="Tool name for NCBI tracking")

    # Rate limiting
    rate_limit_without_key: float = Field(0.34, description="Seconds per request without API key (~3 req/s)")
    rate_limit_with_key: float = Field(0.1, description="Seconds per request with API key (~10 req/s)")

    @property
    def rate_limit(self) -> float:
        """Get the appropriate rate limit based on API key availability."""
        return self.rate_limit_with_key if self.api_key else self.rate_limit_without_key

    model_config = SettingsConfigDict(env_prefix="NCBI_")


class ZhipuConfig(BaseSettings):
    """Zhipu AI API configuration."""

    api_key: str = Field(..., description="Zhipu API key")
    model: str = Field("glm-4-flash", description="Model to use (glm-4, glm-4-flash, glm-4-plus)")
    temperature: float = Field(0.1, ge=0.0, le=1.0, description="Temperature for generation")
    max_tokens: int = Field(4096, description="Maximum tokens in response")
    rate_limit: float = Field(0.5, description="Seconds per request")
    max_retries: int = Field(3, description="Maximum retry attempts")
    use_coding_plan: bool = Field(True, description="Use Coding Plan endpoint (default: True)")

    model_config = SettingsConfigDict(env_prefix="ZHIPU_")


class SearchConfig(BaseSettings):
    """Literature search configuration."""

    max_results: int = Field(100, ge=1, le=10000, description="Maximum results to return")
    batch_size: int = Field(200, ge=1, le=500, description="Batch size for fetching")
    date_range: Optional[List[str]] = Field(None, description="Date range [start, end]")


class DownloadConfig(BaseSettings):
    """Full-text download configuration."""

    sections: List[str] = Field(
        default=["ABSTRACT", "INTRO", "METHODS", "RESULTS", "DISCUSSION", "CONCLUSION"],
        description="Sections to keep"
    )
    timeout: int = Field(30, description="Request timeout in seconds")
    max_retries: int = Field(3, description="Maximum retry attempts")


class ExtractionConfig(BaseSettings):
    """LLM extraction configuration."""

    base_fields: bool = Field(True, description="Extract base fields")
    custom_fields_file: Optional[str] = Field(None, description="Path to custom fields YAML")
    max_retries: int = Field(3, description="Validation retry attempts")
    concurrency: int = Field(5, ge=1, le=20, description="Concurrent extraction tasks")


class OutputConfig(BaseSettings):
    """Output configuration."""

    directory: str = Field("./output", description="Output directory")
    format: str = Field("csv", description="Output format (csv, json, both)")
    include_abstract: bool = Field(False, description="Include abstract in output")
    filename_prefix: str = Field("pubminer_result", description="Output filename prefix")


class CheckpointConfig(BaseSettings):
    """Checkpoint configuration."""

    enabled: bool = Field(True, description="Enable checkpoint/resume")
    directory: str = Field("./output/checkpoints", description="Checkpoint directory")
    auto_resume: bool = Field(True, description="Auto resume interrupted tasks")


class Config(BaseSettings):
    """Main configuration class."""

    ncbi: NCBIConfig = Field(default_factory=NCBIConfig)
    zhipu: ZhipuConfig = Field(default_factory=ZhipuConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file with environment variable substitution."""
        yaml_path = Path(path)

        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Substitute environment variables: ${VAR_NAME} -> value
        def substitute_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        content = re.sub(r"\$\{(\w+)\}", substitute_env, content)

        config_dict = yaml.safe_load(content)

        # Handle nested configuration
        return cls(
            ncbi=NCBIConfig(**config_dict.get("ncbi", {})),
            zhipu=ZhipuConfig(**config_dict.get("zhipu", {})),
            search=SearchConfig(**config_dict.get("search", {})),
            download=DownloadConfig(**config_dict.get("download", {})),
            extraction=ExtractionConfig(**config_dict.get("extraction", {})),
            output=OutputConfig(**config_dict.get("output", {})),
            checkpoint=CheckpointConfig(**config_dict.get("checkpoint", {})),
        )

    def ensure_directories(self):
        """Ensure output and checkpoint directories exist."""
        Path(self.output.directory).mkdir(parents=True, exist_ok=True)
        Path(self.checkpoint.directory).mkdir(parents=True, exist_ok=True)
