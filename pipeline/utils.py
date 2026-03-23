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
            resp.raise_for_status()
            if delay > 0:
                time.sleep(delay)
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return None
