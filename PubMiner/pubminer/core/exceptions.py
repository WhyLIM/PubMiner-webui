"""Custom exception hierarchy for PubMiner."""


class PubMinerError(Exception):
    """Base exception for all PubMiner errors."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(PubMinerError):
    """Configuration related errors."""
    pass


class PubMedAPIError(PubMinerError):
    """NCBI PubMed/E-utilities API errors."""

    def __init__(self, message: str, pmid: str = None, status_code: int = None):
        details = {}
        if pmid:
            details["pmid"] = pmid
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, details)


class BioCAPIError(PubMinerError):
    """NCBI BioC API errors."""

    def __init__(self, message: str, pmcid: str = None, status_code: int = None):
        details = {}
        if pmcid:
            details["pmcid"] = pmcid
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, details)


class LLMExtractionError(PubMinerError):
    """LLM extraction errors."""

    def __init__(
        self,
        message: str,
        pmid: str = None,
        model: str = None,
        raw_response: str = None,
    ):
        details = {}
        if pmid:
            details["pmid"] = pmid
        if model:
            details["model"] = model
        if raw_response:
            details["raw_response"] = raw_response[:500]  # Truncate for logging
        super().__init__(message, details)


class ValidationError(PubMinerError):
    """Data validation errors."""

    def __init__(self, message: str, field: str = None, value: any = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]
        super().__init__(message, details)


class RateLimitError(PubMinerError):
    """Rate limiting errors."""

    def __init__(self, message: str, retry_after: float = None):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(message, details)


class CheckpointError(PubMinerError):
    """Checkpoint/state management errors."""
    pass
