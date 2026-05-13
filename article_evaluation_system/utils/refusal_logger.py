"""
Thread-safe CSV logger for LLM content refusals.

Each refusal is appended as one row to refusals_{run_timestamp}.csv in the
configured output directory (defaults to cwd).
"""

import csv
import json
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_output_path: str | None = None
_header_written: bool = False

_FIELDNAMES = ["timestamp", "agent", "refusal_text", "case_id", "article_url", "extra"]


def set_output_path(directory: str) -> None:
    """Set the directory where refusals_{timestamp}.csv will be written.

    Call once at startup before any evaluations run.

    Args:
        directory: Directory path. The file will be named
                   refusals_{YYYYMMDD_HHMMSS}.csv inside it.
    """
    global _output_path, _header_written
    with _lock:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _output_path = os.path.join(directory, f"refusals_{timestamp}.csv")
        _header_written = False


def _get_output_path() -> str:
    """Return the configured path, falling back to cwd if not set."""
    global _output_path, _header_written
    if _output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _output_path = f"refusals_{timestamp}.csv"
        _header_written = False
    return _output_path


def log_refusal(agent: str, refusal_text: str, context: dict) -> None:
    """Append one refusal row to the CSV log.

    Args:
        agent: Agent class name (e.g. "RelevanceAgent").
        refusal_text: First 200 chars of the LLM refusal response.
        context: Dict with optional keys case_id, article_url, plus any extras.
    """
    global _header_written

    case_id = context.get("case_id", "")
    article_url = context.get("article_url", "")
    extra_keys = {k: v for k, v in context.items() if k not in ("case_id", "article_url")}
    extra = json.dumps(extra_keys) if extra_keys else ""

    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "refusal_text": refusal_text[:200],
        "case_id": case_id,
        "article_url": article_url,
        "extra": extra,
    }

    with _lock:
        path = _get_output_path()
        write_header = not _header_written
        try:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
                if write_header:
                    writer.writeheader()
                    _header_written = True
                writer.writerow(row)
            logger.debug(f"[refusal_logger] Logged refusal from {agent} to {path}")
        except Exception as e:
            logger.warning(f"[refusal_logger] Failed to write refusal log: {e}")
