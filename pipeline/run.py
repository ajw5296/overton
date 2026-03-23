"""Pipeline orchestrator - runs all stages in sequence.

Usage:
    python -m pipeline.run --all
    python -m pipeline.run --stage openalex
    python -m pipeline.run --stage rmd
    python -m pipeline.run --stage overton
    python -m pipeline.run --stage export
    python -m pipeline.run --all --max-researchers 50
    python -m pipeline.run --all --incremental
"""

import argparse
import logging
import sys
import io

from . import config
from .utils import load_json
from . import openalex_stage, rmd_stage, overton_stage, export_stage

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


def main():
    parser = argparse.ArgumentParser(
        description="PSU Research Impact Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pipeline.run --all                    Full run (all stages)
  python -m pipeline.run --stage openalex         Only Stage 1
  python -m pipeline.run --all --max-researchers 50  Test with 50 researchers
  python -m pipeline.run --all --incremental      Skip recently fetched
        """,
    )
    parser.add_argument("--all", action="store_true", help="Run all stages")
    parser.add_argument("--stage", choices=["openalex", "rmd", "overton", "export"],
                        help="Run a single stage")
    parser.add_argument("--max-researchers", type=int, default=None,
                        help="Limit number of researchers (for testing)")
    parser.add_argument("--current-only", action="store_true",
                        help="Only fetch researchers currently at PSU")
    parser.add_argument("--incremental", action="store_true",
                        help="Skip records fetched within the last N days")
    parser.add_argument("--skip-no-hits", action="store_true",
                        help="Overton: skip ORCIDs with zero hits from prior runs")

    args = parser.parse_args()

    if not args.all and not args.stage:
        parser.print_help()
        return

    researchers = None

    # Stage 1: OpenAlex
    if args.all or args.stage == "openalex":
        print("\n" + "=" * 60)
        print("STAGE 1: OpenAlex Fetch")
        print("=" * 60)
        researchers = openalex_stage.run(
            max_researchers=args.max_researchers,
            current_only=args.current_only,
            incremental=args.incremental,
        )

    # Stage 2: RMD Enrichment
    if args.all or args.stage == "rmd":
        print("\n" + "=" * 60)
        print("STAGE 2: RMD Enrichment")
        print("=" * 60)
        if researchers is None:
            researchers = load_json(config.DATA_DIR / config.OPENALEX_OUTPUT, [])
            if not researchers:
                print("ERROR: No Stage 1 data found. Run openalex stage first.")
                return
            print(f"Loaded {len(researchers)} researchers from Stage 1 output")
        researchers = rmd_stage.run(researchers, incremental=args.incremental)

    # Stage 3: Overton Enrichment
    if args.all or args.stage == "overton":
        print("\n" + "=" * 60)
        print("STAGE 3: Overton Enrichment")
        print("=" * 60)
        if researchers is None:
            # Try Stage 2 output first, then Stage 1
            for fname in [config.RMD_OUTPUT, config.OPENALEX_OUTPUT]:
                path = config.DATA_DIR / fname
                if path.exists():
                    researchers = load_json(path, [])
                    print(f"Loaded {len(researchers)} researchers from {fname}")
                    break
            if not researchers:
                print("ERROR: No prior stage data found. Run earlier stages first.")
                return
        researchers = overton_stage.run(
            researchers,
            incremental=args.incremental,
            skip_no_hits=args.skip_no_hits,
        )

    # Stage 4: Export
    if args.all or args.stage == "export":
        print("\n" + "=" * 60)
        print("STAGE 4: Export")
        print("=" * 60)
        export_stage.run(researchers)

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
