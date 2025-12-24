"""
Shared utility functions for ETL scripts.
"""

import json
from pathlib import Path
from typing import Any
from datetime import datetime


def format_number(n: int) -> str:
    """Format a number with thousands separator."""
    return f"{n:,}"


def format_percent(value: float, decimals: int = 1) -> str:
    """Format a value as a percentage string."""
    return f"{value:.{decimals}f}%"


def safe_json_dump(obj: Any, filepath: Path, indent: int = 2) -> None:
    """
    Safely write JSON to a file, handling datetime and other special types.
    """
    def json_serializer(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, 'tolist'):  # numpy arrays
            return o.tolist()
        if hasattr(o, 'item'):  # numpy scalars
            return o.item()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=indent, default=json_serializer, ensure_ascii=False)


def load_json(filepath: Path) -> Any:
    """Load JSON from a file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def file_size_str(size_bytes: int) -> str:
    """Convert file size to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def print_header(title: str, char: str = "=", width: int = 60) -> None:
    """Print a formatted header."""
    print(char * width)
    print(title)
    print(char * width)


def print_subheader(title: str, char: str = "-", width: int = 60) -> None:
    """Print a formatted subheader."""
    print(f"\n{title}")
    print(char * len(title))


def progress_bar(current: int, total: int, width: int = 40, prefix: str = "") -> str:
    """Generate a text-based progress bar."""
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"{prefix}[{bar}] {pct:.0%} ({current}/{total})"
