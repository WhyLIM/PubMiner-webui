"""
Zhipu AI (智谱) API client for structured extraction.

Provides async access to GLM-4 models for information extraction.
"""

import asyncio
import json
from typing import Dict, List, Optional, Type, Any, Union
from pydantic import BaseModel, ValidationError

from pubminer.core.exceptions import LLMExtractionError
from pubminer.core.logger import get_logger
from pubminer.downloader.models import FullTextDocument

logger = get_logger("extractor")


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, min_interval: float = 0.5):
        """
        Initialize rate limiter.

        Args:
            min_interval: Minimum seconds between requests
        """
        self.min_interval = min_interval
        self._last_call_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until we can make the next request."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_call_time

            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)

            self._last_call_time = asyncio.get_event_loop().time()


class ZhipuExtractor:
    """
    Zhipu AI API client for structured information extraction.

    Uses GLM-4 models with JSON output mode for reliable structured extraction.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4-flash",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 3,
        rate_limit: float = 0.5,
        use_coding_plan: bool = True,
    ):
        """
        Initialize the Zhipu extractor.

        Args:
            api_key: Zhipu API key
            model: Model name (glm-4, glm-4-flash, glm-4-plus)
            temperature: Generation temperature (lower = more deterministic)
            max_tokens: Maximum tokens in response
            max_retries: Maximum retry attempts for validation failures
            rate_limit: Seconds between API calls
            use_coding_plan: Whether to use Coding Plan endpoint (default: True)
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(rate_limit)
        self.use_coding_plan = use_coding_plan

        # Import zhipuai
        try:
            from zhipuai import ZhipuAI

            # Set base URL based on endpoint type
            if use_coding_plan:
                # Coding Plan 专属端点
                base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
                logger.info("Using Coding Plan endpoint (专属端点)")
            else:
                # Standard endpoint (通用 API 端点)
                base_url = None  # Use default: https://open.bigmodel.cn/api/paas/v4

            self.client = ZhipuAI(api_key=api_key, base_url=base_url)
        except ImportError:
            raise ImportError("zhipuai package not installed. Run: pip install zhipuai")

        logger.info(f"Zhipu extractor initialized (model={model}, coding_plan={use_coding_plan})")

    def _build_system_prompt(
        self,
        schema_model: Type[BaseModel],
        additional_instructions: str = "",
    ) -> str:
        """
        Build the system prompt with JSON schema.

        Args:
            schema_model: Pydantic model defining the extraction schema
            additional_instructions: Extra domain-specific instructions

        Returns:
            System prompt string
        """
        # Get JSON schema from Pydantic model
        json_schema = schema_model.model_json_schema()

        # Format schema for LLM
        schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)

        # Extract field descriptions
        properties = json_schema.get("properties", {})
        string_fields = [
            field_name for field_name, field_info in properties.items()
            if field_info.get("type") == "string"
        ]

        prompt = f"""You are a medical literature analyst. Your task is to extract structured information from the provided research article.

## Output requirements

1. Return valid JSON only and follow the JSON Schema exactly.
2. Fill every field. If a field is not mentioned, use "Not mentioned".
3. Prioritize factual accuracy. Do not invent or infer unsupported details.
4. Write concise values in English by default.
5. Preserve original terminology only for exact proper nouns, assay names, genes, proteins, or quoted terms.

## Field guidance

Use the following extraction guidance for each field:

"""

        # Add field descriptions
        for field_name, field_info in properties.items():
            description = field_info.get("description", field_name)
            prompt += f"- **{field_name}**: {description}\n"

        if additional_instructions:
            prompt += f"\n## Domain-specific instructions\n\n{additional_instructions}\n"

        prompt += f"""
## JSON Schema

```json
{schema_str}
```

## Important reminders

- Return a raw JSON object only. Do not wrap it in Markdown.
- Ensure the output can be parsed by a standard JSON parser.
- Use English for field values by default.
- When information is missing, use exactly "Not mentioned".
- For text fields, always return a single plain string. Do not return arrays, bullet lists, or nested objects.
- If you want to mention multiple findings or methods, combine them into one concise sentence separated by semicolons.
"""
        if string_fields:
            prompt += "\n## String-only fields\n\n"
            prompt += (
                "The following fields must each be a single string value: "
                + ", ".join(string_fields)
                + ".\n"
            )
        return prompt

    def _build_user_prompt(self, text: str, title: str = "") -> str:
        """
        Build the user prompt with article content.

        Args:
            text: Article text content
            title: Article title (optional)

        Returns:
            User prompt string
        """
        # Truncate text if too long
        max_chars = 12000

        if len(text) > max_chars:
            truncated_text = text[:max_chars]
            # Try to truncate at a paragraph boundary
            last_para = truncated_text.rfind("\n\n")
            if last_para > max_chars * 0.8:
                truncated_text = truncated_text[:last_para]
            truncated_text += "\n\n...[Text truncated. Extract information based on the content above.]..."
        else:
            truncated_text = text

        prompt = "Extract structured information from the following article content.\n\n"

        if title:
            prompt += f"Article title: {title}\n\n"

        prompt += f"""---
{truncated_text}
---

Return the extraction result in the required JSON Schema format.
Remember:
1. Return a raw JSON object only.
2. Fill every field.
3. Use "Not mentioned" for missing information.
4. Use English for field values by default.
5. For every text field, return one plain string value, not an array or object.
"""
        return prompt

    def _normalize_output_language(self, value: Any) -> Any:
        """Normalize common placeholder values to the default English output style."""
        if isinstance(value, str):
            normalized = value.strip()
            if normalized in {"未提及", "未提到", "未说明", "未知", "不适用"}:
                return "Not mentioned"
            return value

        if isinstance(value, list):
            return [self._normalize_output_language(item) for item in value]

        if isinstance(value, dict):
            return {key: self._normalize_output_language(item) for key, item in value.items()}

        return value

    def _sanitize_result_for_schema(
        self,
        result: Dict[str, Any],
        schema_model: Type[BaseModel],
    ) -> Dict[str, Any]:
        """Coerce common non-string model outputs into schema-compatible values."""
        if not isinstance(result, dict):
            return result

        sanitized = dict(result)
        schema = schema_model.model_json_schema()
        properties = schema.get("properties", {})

        for field_name, field_schema in properties.items():
            if field_name not in sanitized:
                continue

            expected_type = field_schema.get("type")
            value = sanitized[field_name]

            if expected_type == "string":
                sanitized[field_name] = self._coerce_to_string(value)

        return sanitized

    def _coerce_to_string(self, value: Any) -> str:
        """Convert list/dict/scalar values to stable strings for string fields."""
        if value is None:
            return "Not mentioned"

        if isinstance(value, str):
            stripped = value.strip()
            return stripped or "Not mentioned"

        if isinstance(value, list):
            parts = [self._coerce_to_string(item) for item in value]
            parts = [part for part in parts if part and part != "Not mentioned"]
            return "; ".join(parts) if parts else "Not mentioned"

        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                coerced = self._coerce_to_string(item)
                if coerced and coerced != "Not mentioned":
                    parts.append(f"{key}: {coerced}")
            return "; ".join(parts) if parts else "Not mentioned"

        return str(value)

    async def extract(
        self,
        text: str,
        schema_model: Type[BaseModel],
        title: str = "",
        pmid: str = "",
    ) -> Dict[str, Any]:
        """
        Extract structured information from text.

        Args:
            text: Article text to extract from
            schema_model: Pydantic model defining extraction schema
            title: Article title (optional, helps context)
            pmid: PubMed ID for logging (optional)

        Returns:
            Dictionary with extracted fields
        """
        # Get additional instructions if attached to model
        additional_instructions = getattr(schema_model, "_additional_instructions", "")

        system_prompt = self._build_system_prompt(schema_model, additional_instructions)
        user_prompt = self._build_user_prompt(text, title)

        last_error = None
        raw_response = ""

        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                await self.rate_limiter.acquire()

                # Call API (zhipuai SDK is synchronous, so we wrap it)
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                raw_response = response.choices[0].message.content

                # Clean response (remove markdown code blocks if present)
                cleaned_response = raw_response.strip()
                if cleaned_response.startswith("```"):
                    # Remove code block markers
                    lines = cleaned_response.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned_response = "\n".join(lines).strip()

                # Parse JSON
                result = json.loads(cleaned_response)
                result = self._sanitize_result_for_schema(result, schema_model)

                # Validate with Pydantic
                validated = schema_model(**result)

                logger.debug(f"Successfully extracted data for PMID {pmid}")

                return self._normalize_output_language(validated.model_dump())

            except json.JSONDecodeError as e:
                last_error = f"JSON parsing error: {e}"
                logger.warning(f"JSON parse error for {pmid} (attempt {attempt + 1}): {e}")

                # Try to fix common JSON issues
                try:
                    # Sometimes LLM adds trailing commas
                    fixed = cleaned_response.replace(",}", "}").replace(",]", "]")
                    result = json.loads(fixed)
                    result = self._sanitize_result_for_schema(result, schema_model)
                    validated = schema_model(**result)
                    return self._normalize_output_language(validated.model_dump())
                except Exception:
                    pass

            except ValidationError as e:
                last_error = f"Validation error: {e}"
                logger.warning(f"Validation error for {pmid} (attempt {attempt + 1}): {e}")

                # Try to fill missing fields with defaults
                try:
                    if isinstance(result, dict):
                        result = self._sanitize_result_for_schema(result, schema_model)
                        # Create model with partial data
                        validated = schema_model.model_validate(result)
                        return self._normalize_output_language(validated.model_dump())
                except Exception:
                    pass

            except Exception as e:
                last_error = str(e)
                logger.error(f"Extraction error for {pmid} (attempt {attempt + 1}): {e}")

            # Wait before retry
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        # All retries failed
        return {
            "error": last_error,
            "raw_response": raw_response[:500] if raw_response else "",
            "pmid": pmid,
        }

    async def batch_extract(
        self,
        documents: List[Union[Dict[str, str], FullTextDocument]],
        schema_model: Type[BaseModel],
        concurrency: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Extract information from multiple documents.

        Args:
            documents: List of dicts or FullTextDocument objects
            schema_model: Pydantic model for extraction
            concurrency: Maximum concurrent extractions

        Returns:
            List of extraction results
        """
        semaphore = asyncio.Semaphore(concurrency)

        def get_document_value(doc: Union[Dict[str, str], FullTextDocument], key: str) -> str:
            if isinstance(doc, dict):
                return str(doc.get(key, "") or "")

            if key == "text":
                return doc.filtered_text or ""

            return str(getattr(doc, key, "") or "")

        async def limited_extract(doc: Union[Dict[str, str], FullTextDocument]) -> Dict[str, Any]:
            async with semaphore:
                result = await self.extract(
                    text=get_document_value(doc, "text"),
                    schema_model=schema_model,
                    title=get_document_value(doc, "title"),
                    pmid=get_document_value(doc, "pmid"),
                )
                result["pmid"] = get_document_value(doc, "pmid")
                return result

        tasks = [limited_extract(doc) for doc in documents]
        results = await asyncio.gather(*tasks)

        # Count successes and failures
        successes = sum(1 for r in results if "error" not in r)
        failures = len(results) - successes

        logger.info(f"Batch extraction complete: {successes} success, {failures} failed")

        return results

    def extract_sync(
        self,
        text: str,
        schema_model: Type[BaseModel],
        title: str = "",
        pmid: str = "",
    ) -> Dict[str, Any]:
        """
        Synchronous extraction method for simple use cases.

        Args:
            text: Article text
            schema_model: Pydantic model for extraction
            title: Article title
            pmid: PubMed ID

        Returns:
            Extraction result dictionary
        """
        return asyncio.run(
            self.extract(text, schema_model, title, pmid)
        )
