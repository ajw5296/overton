"""Drop the pipeline data tables for a clean cut-over re-run.

Drops: researchers, articles, article_citations, policy_documents.
Preserves: pipeline_metadata (run history) and S3 PDF objects.

After running this, do:
    python -m pipeline.run --rebuild-map
    python -m pipeline.run --all

Run: python -m scripts.drop_pipeline_tables --confirm
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from pipeline.db.connection import get_engine

# Order matters — child (FK referrer) first.
TABLES_TO_DROP = [
    "article_citations",
    "articles",
    "policy_documents",
    "researchers",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="Required to actually drop. Without it, only previews.")
    args = parser.parse_args()

    engine = get_engine()
    if not args.confirm:
        print("DRY RUN — no changes made. Pass --confirm to actually drop.\n")

    with engine.connect() as conn:
        # Show row counts so we know what's about to be lost
        for table in TABLES_TO_DROP + ["pipeline_metadata"]:
            try:
                n = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                marker = "DROP " if table in TABLES_TO_DROP else "keep "
                print(f"  {marker}{table:<20} ({n:,} rows)")
            except Exception as e:
                print(f"  ?     {table:<20} (error: {e})")

    if not args.confirm:
        return

    print("\nDropping...")
    with engine.begin() as conn:
        for table in TABLES_TO_DROP:
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            print(f"  dropped {table}")

    print("\nDone. Next:")
    print("  python -m pipeline.run --rebuild-map")
    print("  python -m pipeline.run --all")


if __name__ == "__main__":
    main()
