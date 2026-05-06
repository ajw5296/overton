"""Shared utilities - I/O, rate limiting, retry logic."""

import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger("pipeline")


def now_iso() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def days_since(iso_timestamp: str) -> float:
    """Return days elapsed since the given ISO timestamp."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        return float("inf")


def load_json(path: Path, default=None):
    """Load JSON from a file, returning default if it doesn't exist."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(data, path: Path, compact: bool = False):
    """Save data to JSON. Use compact=True for large files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
    size_mb = path.stat().st_size / (1024 * 1024)
    logger.info(f"Saved {path.name} ({size_mb:.1f} MB)")


def normalize_date(date_str: str | None) -> str | None:
    """Normalize a date string to ISO 8601 format (YYYY-MM-DD).

    Handles:
    - Full ISO 8601 with timezone: 2020-05-18T00:00:00+00:00
    - Date only: 2020-05-18
    - Returns None for empty/invalid input
    """
    if not date_str:
        return None
    try:
        # Try full ISO parse first
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    # Already in YYYY-MM-DD format or unparseable
    if len(date_str) >= 10 and date_str[:4].isdigit():
        return date_str[:10]
    return date_str


def cast_bool(val) -> bool:
    """Cast a value to bool, handling string 'true'/'false' from Overton API."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() == "true"
    return bool(val)


def api_request(url: str, params: dict = None, headers: dict = None,
                delay: float = 0, max_retries: int = 3, timeout: int = 30) -> dict | None:
    """Make a GET request with retry and rate-limit handling."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 5, 60)
                logger.warning(f"Rate limited (429). Waiting {wait}s...")
                time.sleep(wait)
                continue
            # Don't retry client errors (4xx) — they won't succeed on retry
            if 400 <= resp.status_code < 500:
                if resp.status_code != 429:
                    logger.debug(f"Client error {resp.status_code} for {url}")
                    return None
            resp.raise_for_status()
            if delay > 0:
                time.sleep(delay)
            # Empty / non-JSON bodies can come back from upstream APIs even on
            # 200 OK (e.g. transient gateway hiccups). Treat as a failed attempt
            # and retry rather than letting JSONDecodeError kill the whole stage.
            if not resp.text.strip():
                logger.warning(f"Empty response body (attempt {attempt + 1}/{max_retries}) for {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            try:
                return resp.json()
            except ValueError as e:
                logger.warning(f"Non-JSON response (attempt {attempt + 1}/{max_retries}) for {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return None
