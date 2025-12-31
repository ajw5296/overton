"""
Metrics module for Overton policy document analysis.
Designed to be Streamlit-ready with clean data loading and aggregation functions.
"""

import json
from collections import defaultdict
from pathlib import Path

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data" / "overton_exports"
POLICY_DOCS_FILE = DATA_DIR / "social_science_overton_policy_documents.json"
ARTICLES_FILE = DATA_DIR / "social_science_overton_articles.json"


def load_policy_documents(filepath=POLICY_DOCS_FILE):
    """Load the policy documents JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_source_types_by_subfield(data=None):
    """
    Group researchers by their subfield and count the source types
    of policy documents citing their work.

    Returns:
        dict: {subfield: {source_type: count}}
    """
    if data is None:
        data = load_policy_documents()

    subfield_source_counts = defaultdict(lambda: defaultdict(int))

    for researcher in data:
        # Get the researcher's subfield
        field_info = researcher.get("field_of_research", {})
        subfield = field_info.get("subfield", "Unknown")

        # Get all policy documents for this researcher
        policy_docs = researcher.get("policy_documents", {})
        results = policy_docs.get("results", [])

        # Count source types
        for doc in results:
            source = doc.get("source", {})
            source_type = source.get("type", "Unknown")
            subfield_source_counts[subfield][source_type] += 1

    # Convert to regular dict for cleaner output
    return {subfield: dict(counts) for subfield, counts in subfield_source_counts.items()}


def print_source_types_by_subfield(results=None):
    """Pretty print the source types by subfield."""
    if results is None:
        results = get_source_types_by_subfield()

    for domain, source_counts in sorted(results.items()):
        print(f"\n{'='*60}")
        print(f"SUBFIELD: {domain}")
        print(f"{'='*60}")

        # Sort by count descending
        sorted_counts = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
        total = sum(count for _, count in sorted_counts)

        print(f"{'Source Type':<30} {'Count':>10} {'Percent':>10}")
        print("-" * 52)

        for source_type, count in sorted_counts:
            pct = (count / total) * 100
            print(f"{source_type:<30} {count:>10,} {pct:>9.1f}%")

        print("-" * 52)
        print(f"{'TOTAL':<30} {total:>10,}")


if __name__ == "__main__":
    print("Loading policy documents data...")
    data = load_policy_documents()
    print(f"Loaded {len(data)} researchers\n")

    print("Analyzing source types by subfield...")
    results = get_source_types_by_subfield(data)

    print_source_types_by_subfield(results)
