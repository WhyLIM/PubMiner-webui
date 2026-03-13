#!/usr/bin/env python3
"""
PubMiner - Main Entry Point

Quick entry point for running PubMiner directly.
For full CLI options, use: python -m pubminer.cli.main --help
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pubminer.cli.main import main

if __name__ == "__main__":
    main()
