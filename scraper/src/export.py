"""
Export contacts to CSV / JSON.
"""
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

from models import Contact

logger = logging.getLogger(__name__)


def to_csv(contacts: list[Contact], output_dir: str = "output", filename: str = "") -> str:
    """Export contacts to CSV. Returns file path."""
    if not contacts:
        logger.warning("No contacts to export.")
        return ""

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contacts_{ts}.csv"

    filepath = str(Path(output_dir) / filename)
    df = pd.DataFrame([c.to_dict() for c in contacts])

    # Sort by confidence score descending
    df = df.sort_values("confidence_score", ascending=False)

    df.to_csv(filepath, index=False, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
    logger.info(f"Exported {len(contacts)} contacts to {filepath}")
    return filepath


def to_json(contacts: list[Contact], output_dir: str = "output", filename: str = "") -> str:
    """Export contacts to JSON. Returns file path."""
    if not contacts:
        return ""

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"contacts_{ts}.json"

    filepath = str(Path(output_dir) / filename)
    data = [c.to_dict() for c in contacts]
    data.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Exported {len(contacts)} contacts to {filepath}")
    return filepath


def print_summary(contacts: list[Contact]):
    """Print a summary table to the console."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"Contacts Found ({len(contacts)} total)", show_lines=True)
        table.add_column("Name", style="bold cyan", max_width=25)
        table.add_column("Title", max_width=30)
        table.add_column("Company", max_width=20)
        table.add_column("Email", style="green", max_width=30)
        table.add_column("Phone", style="yellow", max_width=15)
        table.add_column("Score", justify="right")
        table.add_column("Source", max_width=20)

        for c in sorted(contacts, key=lambda x: x.confidence_score, reverse=True)[:50]:
            table.add_row(
                c.full_name or "-",
                c.job_title[:30] if c.job_title else "-",
                c.company[:20] if c.company else "-",
                c.email or "-",
                c.phone or "-",
                f"{c.confidence_score:.2f}",
                c.source[:20] if c.source else "-",
            )

        console.print(table)
    except ImportError:
        for c in contacts[:20]:
            print(f"{c.full_name} | {c.job_title} | {c.email} | {c.phone} | score={c.confidence_score}")
