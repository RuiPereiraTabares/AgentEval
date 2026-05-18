"""
Thread-safe CSV logger for non-200 HTTP responses.

Each failed request (and its eventual retry outcome) is appended as one row
to http_errors_{run_timestamp}.csv in the configured output directory.
"""

import csv
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_output_path: str | None = None
_header_written: bool = False

_FIELDNAMES = [
    "timestamp",
    "status_code",
    "endpoint",
    "attempt_number",
    "max_attempts",
    "error_body",
    "retry_helped",
    "case_id",
]


def set_output_path(directory: str) -> None:
    """Set the directory where http_errors_{timestamp}.csv will be written.

    Call once at startup before any evaluations run.
    """
    global _output_path, _header_written
    with _lock:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _output_path = os.path.join(directory, f"http_errors_{timestamp}.csv")
        _header_written = False


def _get_output_path() -> str:
    global _output_path, _header_written
    if _output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _output_path = f"http_errors_{timestamp}.csv"
        _header_written = False
    return _output_path


def get_output_path() -> str | None:
    """Return the current HTTP error log path (None if not yet initialised)."""
    return _output_path


def log_http_errors(
    failed_attempts: list[tuple[int, int, str]],
    endpoint: str,
    max_attempts: int,
    retry_helped: bool,
    case_id: str = "",
) -> None:
    """Write one row per failed attempt to the HTTP error CSV.

    Args:
        failed_attempts: List of (attempt_number, status_code, error_body) tuples.
        endpoint: The URL that was called.
        max_attempts: Total attempts configured (initial + retries).
        retry_helped: True if a later attempt succeeded; False if all failed.
        case_id: Optional case identifier for context.
    """
    global _header_written

    rows = [
        {
            "timestamp": datetime.utcnow().isoformat(),
            "status_code": status_code,
            "endpoint": endpoint,
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "error_body": error_body[:500],
            "retry_helped": str(retry_helped),
            "case_id": case_id,
        }
        for attempt_number, status_code, error_body in failed_attempts
    ]

    if not rows:
        return

    with _lock:
        path = _get_output_path()
        write_header = not _header_written
        try:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
                if write_header:
                    writer.writeheader()
                    _header_written = True
                writer.writerows(rows)
            logger.debug(f"[http_error_logger] Logged {len(rows)} error row(s) to {path}")
        except Exception as e:
            logger.warning(f"[http_error_logger] Failed to write HTTP error log: {e}")
