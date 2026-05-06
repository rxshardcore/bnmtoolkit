"""Generate structured JSON / CSV reports per run."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def save_json_report(data: dict, output_dir: Path, run_id: int) -> Path:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"run_{run_id}.json"
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    logger.info("JSON report written to %s", path)
    return path


def save_csv_export(rows: list[dict], output_dir: Path, run_id: int, name: str) -> Path:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"run_{run_id}_{name}.csv"
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("CSV export written to %s (%d rows)", path, len(rows))
    return path
