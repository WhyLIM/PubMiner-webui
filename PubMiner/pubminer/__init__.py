"""
PubMiner: 智能医学文献批量挖掘与结构化分析工具

A modular, high-concurrency medical literature mining tool based on Python and LLM.
"""

__version__ = "0.1.0"
__author__ = "PubMiner Team"

from pubminer.core.config import Config
from pubminer.core.state import StateManager

__all__ = ["Config", "StateManager", "__version__"]
