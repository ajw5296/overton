"""Pipeline orchestrator - runs all stages in sequence.

Usage:
    python -m pipeline.run --all
    python -m pipeline.run --stage rmd
    python -m pipeline.run --stage openalex
    python -m pipeline.run --stage overton-articles
    python -m pipeline.run --stage overton-documents
    python -m pipeline.run --stage download
    python -m pipeline.run --stage export
    python -m pipeline.run --all --max-researchers 50
    python -m pipeline.run --all --incremental
    python -m pipeline.run --rebuild-map
"""

import argparse
import logging
import sys
import io
import uuid
from datetime import datetime, timezone

from . import config
from .utils import load_json
from . import (
    openalex_stage,
    rmd_stage,
    overton_articles_stage,
    overton_documents_stage,
    document_download_stage,
    export_stage,
)

# Force UTF-8 output for Windows terminals
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.PROJECT_ROOT / "pipeline.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("pipeline")


STAGES = [
    "rmd",
    "openalex",
    "overton-articles",
    "overton-documents",
    "download",
    "export",
]


def _record_run(run_id: str, stage: str, status: str, stats: dict | None = None,
                started_at: datetime | None = None):
    """Record pipeline run metadata to the database (best-effort)."""
    try:
        from .db.operations import record_pipeline_run
        record_pipeline_run(
            run_id=run_id,
            stage=stage,
            status=status,
            stats=stats,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc) if status in ("completed", "failed") else None,
        )
    except Exception as e:
        logger.warning("Failed to record pipeline metadata: %s", e)


def _init_db():
    """Initialize database tables (best-effort)."""
    try:
        from .db.schema import ensure_tables
        ensure_tables()
        logger.info("Database tables initialized")
        return True
    except Exception as e:
        logger.warning("Database not available, running in file-only mode: %s", e)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="PSU Research Impact Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pipeline.run --all                         Full run (all stages)
  python -m pipeline.run --stage rmd                   Only Stage 1 (RMD cohort)
  python -m pipeline.run --stage openalex              Only Stage 2 (OpenAlex enrich)
  python -m pipeline.run --stage overton-articles      Only Stage 3
  python -m pipeline.run --all --max-researchers 50    Test with 50
  python -m pipeline.run --all --incremental           Skip recently fetched
  python -m pipeline.run --stage download --max-downloads 10  Test PDF download
  python -m pipeline.run --rebuild-map                 Rebuild ORCID->WebAccess map
        """,
    )
    parser.add_argument("--all", action="store_true", help="Run all stages")
    parser.add_argument("--stage", choices=STAGES, help="Run a single stage")
    parser.add_argument("--rebuild-map", action="store_true",
                        help="Rebuild the ORCID->WebAccess map (expensive, ~20 min)")
    parser.add_argument("--run-id", type=str, default=None,
                        help="Pipeline run ID (default: auto-generated UUID)")
    parser.add_argument("--max-researchers", type=int, default=None,
                        help="Limit number of researchers (for testing)")
    parser.add_argument("--max-downloads", type=int, default=None,
                        help="Limit number of PDF downloads (for testing)")
    parser.add_argument("--incremental", action="store_true",
                        help="Skip records fetched within the last N days")
    parser.add_argument("--skip-no-hits", action="store_true",
                        help="Overton: skip ORCIDs with zero hits from prior runs")
    parser.add_argument("--skip-export", action="store_true",
                        help="Skip the export stage (when dashboard reads from DB)")

    args = parser.parse_args()

    # Handle rebuild-map separately
    if args.rebuild_map:
        _init_db()
        rmd_stage.rebuild_orcid_map()
        return

    if not args.all and not args.stage:
        parser.print_help()
        return

    run_id = args.run_id or str(uuid.uuid4())[:8]
    logger.info("Pipeline run %s starting", run_id)

    # Initialize database
    db_available = _init_db()

    # Stage 1: RMD Researcher Cohort
    if args.all or args.stage == "rmd":
        print("\n" + "=" * 60)
        print("STAGE 1: RMD Researcher Cohort")
        print("=" * 60)
        started = datetime.now(timezone.utc)
        _record_run(run_id, "rmd", "started", started_at=started)
        try:
            stats = rmd_stage.run(
                max_researchers=args.max_researchers,
                incremental=args.incremental,
            )
            _record_run(run_id, "rmd", "completed", stats=stats, started_at=started)
        except Exception as e:
            logger.error("Stage 1 failed: %s", e, exc_info=True)
            _record_run(run_id, "rmd", "failed", stats={"error": str(e)}, started_at=started)
            if args.stage:
                return

    # Stage 2: OpenAlex Enrichment
    if args.all or args.stage == "openalex":
        print("\n" + "=" * 60)
        print("STAGE 2: OpenAlex Enrichment")
        print("=" * 60)
        started = datetime.now(timezone.utc)
        _record_run(run_id, "openalex", "started", started_at=started)
        try:
            stats = openalex_stage.run(
                max_researchers=args.max_researchers,
                incremental=args.incremental,
            )
            _record_run(run_id, "openalex", "completed", stats=stats, started_at=started)
        except Exception as e:
            logger.error("Stage 2 failed: %s", e, exc_info=True)
            _record_run(run_id, "openalex", "failed", stats={"error": str(e)}, started_at=started)
            if args.stage:
                return

    # Stage 3: Overton Articles
    if args.all or args.stage == "overton-articles":
        print("\n" + "=" * 60)
        print("STAGE 3: Overton Articles Fetch")
        print("=" * 60)
        started = datetime.now(timezone.utc)
        _record_run(run_id, "overton-articles", "started", started_at=started)
        try:
            # Note: --skip-no-hits is a legacy flag from the per-ORCID era and
            # has no effect in the DOI-set flow; accepted but ignored here.
            stats = overton_articles_stage.run(incremental=args.incremental)
            _record_run(run_id, "overton-articles", "completed", stats=stats, started_at=started)
        except Exception as e:
            logger.error("Stage 3 failed: %s", e, exc_info=True)
            _record_run(run_id, "overton-articles", "failed", stats={"error": str(e)}, started_at=started)
            if args.stage:
                return

    # Stage 4: Overton Documents
    if args.all or args.stage == "overton-documents":
        print("\n" + "=" * 60)
        print("STAGE 4: Overton Documents Fetch")
        print("=" * 60)
        started = datetime.now(timezone.utc)
        _record_run(run_id, "overton-documents", "started", started_at=started)
        try:
            stats = overton_documents_stage.run(incremental=args.incremental)
            _record_run(run_id, "overton-documents", "completed", stats=stats, started_at=started)
        except Exception as e:
            logger.error("Stage 4 failed: %s", e, exc_info=True)
            _record_run(run_id, "overton-documents", "failed", stats={"error": str(e)}, started_at=started)
            if args.stage:
                return

    # Stage 5: Document Download
    if args.all or args.stage == "download":
        print("\n" + "=" * 60)
        print("STAGE 5: Document PDF Download")
        print("=" * 60)
        started = datetime.now(timezone.utc)
        _record_run(run_id, "download", "started", started_at=started)
        try:
            stats = document_download_stage.run(max_downloads=args.max_downloads)
            _record_run(run_id, "download", "completed", stats=stats, started_at=started)
        except Exception as e:
            logger.error("Stage 5 failed: %s", e, exc_info=True)
            _record_run(run_id, "download", "failed", stats={"error": str(e)}, started_at=started)
            if args.stage:
                return

    # Stage 6: Export
    if (args.all and not args.skip_export) or args.stage == "export":
        print("\n" + "=" * 60)
        print("STAGE 6: Export")
        print("=" * 60)
        started = datetime.now(timezone.utc)
        _record_run(run_id, "export", "started", started_at=started)
        try:
            stats = export_stage.run()
            _record_run(run_id, "export", "completed", stats=stats, started_at=started)
        except Exception as e:
            logger.error("Stage 6 failed: %s", e, exc_info=True)
            _record_run(run_id, "export", "failed", stats={"error": str(e)}, started_at=started)
            if args.stage:
                return

    print("\n" + "=" * 60)
    print(f"Pipeline run {run_id} complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
