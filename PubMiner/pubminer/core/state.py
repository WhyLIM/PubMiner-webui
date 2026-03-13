"""Checkpoint and state management for resume functionality."""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict
import threading

from pubminer.core.exceptions import CheckpointError


class ProcessingStage(Enum):
    """Processing stages for tracking progress."""
    PENDING = "pending"
    FETCHED = "fetched"
    DOWNLOADED = "downloaded"
    EXTRACTED = "extracted"
    COMPLETED = "completed"
    FAILED = "failed"

    def __lt__(self, other):
        """Compare stages by order."""
        order = [
            ProcessingStage.PENDING,
            ProcessingStage.FETCHED,
            ProcessingStage.DOWNLOADED,
            ProcessingStage.EXTRACTED,
            ProcessingStage.COMPLETED,
            ProcessingStage.FAILED,
        ]
        return order.index(self) < order.index(other)


@dataclass
class PMIDState:
    """State for a single PMID."""
    pmid: str
    stage: str
    has_fulltext: bool = False
    pmcid: Optional[str] = None
    error: Optional[str] = None
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PMIDState":
        return cls(**data)


class StateManager:
    """
    Manages processing state for checkpoint/resume functionality.

    Thread-safe implementation for concurrent access.
    """

    def __init__(self, checkpoint_dir: str = "./output/checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.checkpoint_dir / "processing_state.json"
        self._lock = threading.Lock()
        self._state: Dict = self._load_state()

    def _load_state(self) -> Dict:
        """Load state from checkpoint file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                raise CheckpointError(f"Failed to load checkpoint: {e}")

        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "query": "",
            "pmid_file": "",
            "total_pmids": 0,
            "pmids": {},
        }

    def _save_state(self):
        """Save state to checkpoint file."""
        with self._lock:
            self._state["last_updated"] = datetime.now().isoformat()
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)

    def initialize_run(
        self,
        query: Optional[str] = None,
        pmid_file: Optional[str] = None,
        pmids: Optional[List[str]] = None,
    ):
        """
        Initialize a new processing run.

        Args:
            query: Search query (if using search mode)
            pmid_file: Path to PMID file (if using file mode)
            pmids: List of PMIDs to process
        """
        with self._lock:
            self._state["query"] = query or ""
            self._state["pmid_file"] = pmid_file or ""
            self._state["total_pmids"] = len(pmids) if pmids else 0

            # Initialize PMID states
            if pmids:
                for pmid in pmids:
                    if pmid not in self._state["pmids"]:
                        self._state["pmids"][pmid] = PMIDState(
                            pmid=pmid,
                            stage=ProcessingStage.PENDING.value,
                            updated_at=datetime.now().isoformat(),
                        ).to_dict()

        self._save_state()

    def update_pmid(
        self,
        pmid: str,
        stage: ProcessingStage,
        has_fulltext: bool = False,
        pmcid: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """
        Update the state of a PMID.

        Args:
            pmid: PubMed ID
            stage: Current processing stage
            has_fulltext: Whether full text is available
            pmcid: PMC ID (if available)
            error: Error message (if failed)
        """
        with self._lock:
            state = PMIDState(
                pmid=pmid,
                stage=stage.value,
                has_fulltext=has_fulltext,
                pmcid=pmcid,
                error=error,
                updated_at=datetime.now().isoformat(),
            )
            self._state["pmids"][pmid] = state.to_dict()

        self._save_state()

    def get_pending_pmids(self, target_stage: ProcessingStage) -> List[str]:
        """
        Get PMIDs that haven't reached the target stage.

        Args:
            target_stage: The stage to check against

        Returns:
            List of PMIDs needing processing
        """
        pending = []
        for pmid, data in self._state["pmids"].items():
            current = ProcessingStage(data.get("stage", ProcessingStage.PENDING.value))
            if current.value != ProcessingStage.FAILED.value and current < target_stage:
                pending.append(pmid)
        return pending

    def get_pmids_by_stage(self, stage: ProcessingStage) -> List[str]:
        """Get all PMIDs at a specific stage."""
        return [
            pmid
            for pmid, data in self._state["pmids"].items()
            if data.get("stage") == stage.value
        ]

    def get_pmid_state(self, pmid: str) -> Optional[PMIDState]:
        """Get the state of a specific PMID."""
        data = self._state["pmids"].get(pmid)
        if data:
            return PMIDState.from_dict(data)
        return None

    def get_progress(self) -> Dict:
        """
        Get current processing progress.

        Returns:
            Dictionary with progress statistics
        """
        stages = {stage.value: 0 for stage in ProcessingStage}

        for data in self._state["pmids"].values():
            stage = data.get("stage", ProcessingStage.PENDING.value)
            stages[stage] = stages.get(stage, 0) + 1

        total = self._state["total_pmids"] or len(self._state["pmids"])
        completed = stages.get(ProcessingStage.COMPLETED.value, 0)
        failed = stages.get(ProcessingStage.FAILED.value, 0)

        return {
            "total": total,
            "stages": stages,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
            "progress_percent": round((completed + failed) / total * 100, 1) if total > 0 else 0,
        }

    def get_all_pmids(self) -> List[str]:
        """Get all PMIDs in the current run."""
        return list(self._state["pmids"].keys())

    def clear(self):
        """Clear all state."""
        with self._lock:
            self._state = {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "query": "",
                "pmid_file": "",
                "total_pmids": 0,
                "pmids": {},
            }
        self._save_state()

    def has_previous_run(self) -> bool:
        """Check if there's a previous run to resume."""
        return len(self._state["pmids"]) > 0

    def get_run_info(self) -> Dict:
        """Get information about the current/previous run."""
        return {
            "query": self._state.get("query", ""),
            "pmid_file": self._state.get("pmid_file", ""),
            "created_at": self._state.get("created_at", ""),
            "last_updated": self._state.get("last_updated", ""),
            "total_pmids": self._state.get("total_pmids", 0),
        }
