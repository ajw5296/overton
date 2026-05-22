"""
Overton policy document pull — US state government child welfare documents.

Filters:
- Sector: Public sector
- Organisation type: Government
- Country: USA
- Sources: 49 state/commonwealth sources (per JP Overton Needs.xlsx)
- Published: 2023-01-01 to 2025-12-31
- Query: Child welfare boolean search (from claudeinfo.txt / JP spreadsheet)

Splits by year to avoid Overton's 1000-page (50K doc) API limit.
Expected yield: ~44,226 documents (after state source filtering)
"""

import json
import math
import os
import requests
import time

# Configuration
API_KEY = os.getenv("OVERTON_API_KEY", "7cb1b1-daf77f-94ed27")
DOCUMENTS_URL = "https://app.overton.io/documents.php"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "overton_exports")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "us_gov_child_welfare_2023_2025.json")

# 49 state/commonwealth sources from JP spreadsheet (Rhode Island missing per JP's note)
STATE_SOURCES = [
    "State of Alabama", "State of Alaska", "State of Arizona", "State of Arkansas",
    "State of California", "State of Colorado", "State of Connecticut",
    "State of Delaware", "State of Florida", "State of Georgia",
    "State of Hawaii", "State of Idaho", "State of Illinois", "State of Indiana",
    "State of Iowa", "State of Kansas", "State of Kentucky", "State of Louisiana",
    "State of Maine", "State of Maryland", "Commonwealth of Massachusetts",
    "State of Michigan", "State of Minnesota", "State of Mississippi",
    "State of Missouri", "State of Montana", "State of Nebraska", "State of Nevada",
    "State of New Hampshire", "State of New Jersey", "State of New Mexico",
    "State of New York", "State of North Carolina", "State of North Dakota",
    "State of Ohio", "State of Oklahoma", "State of Oregon",
    "Commonwealth of Pennsylvania", "State of South Carolina", "State of South Dakota",
    "State of Tennessee", "State of Texas", "State of Utah", "State of Vermont",
    "Commonwealth of Virginia", "State of Washington", "State of West Virginia",
    "State of Wisconsin", "State of Wyoming",
]
STATE_SOURCES_LOWER = {s.lower() for s in STATE_SOURCES}

# Child welfare boolean query (from claudeinfo.txt / JP spreadsheet "Columns" tab)
QUERY = (
    '(  "child abuse"~5 OR "abuse child"~5 OR '
    '  "child abused"~5 OR "abused child"~5 OR '
    '  "child abusing"~5 OR "abusing child"~5 OR '
    '  "child abusive"~5 OR "abusive child"~5 OR '
    '   "child\'s abuse"~5 OR "abuse child\'s"~5 OR '
    '  "child\'s abused"~5 OR "abused child\'s"~5 OR '
    '  "child\'s abusing"~5 OR "abusing child\'s"~5 OR '
    '  "child\'s abusive"~5 OR "abusive child\'s"~5 OR '
    '   "children abuse"~5 OR "abuse children"~5 OR '
    '  "children abused"~5 OR "abused children"~5 OR '
    '  "children abusing"~5 OR "abusing children"~5 OR '
    '  "children abusive"~5 OR "abusive children"~5 OR '
    '   "child neglect"~5 OR "neglect child"~5 OR '
    '  "child neglected"~5 OR "neglected child"~5 OR '
    '  "child neglecting"~5 OR "neglecting child"~5 OR '
    '  "child negligent"~5 OR "negligent child"~5 OR '
    '   "child\'s neglect"~5 OR "neglect child\'s"~5 OR '
    '  "child\'s neglected"~5 OR "neglected child\'s"~5 OR '
    '  "child\'s neglecting"~5 OR "neglecting child\'s"~5 OR '
    '  "child\'s negligent"~5 OR "negligent child\'s"~5 OR '
    '   "children neglect"~5 OR "neglect children"~5 OR '
    '  "children neglected"~5 OR "neglected children"~5 OR '
    '  "children neglecting"~5 OR "neglecting children"~5 OR '
    '  "children negligent"~5 OR "negligent children"~5 OR '
    ' "Best interests of the child" OR "best interest of the child" OR '
    ' "Reasonable efforts to prevent removal" OR '
    ' ("imminent danger child"~5 OR "child imminent danger"~5 OR '
    '  "imminent danger children"~5 OR "children imminent danger"~5) OR '
    ' "termination of parental rights" OR '
    ' ("relinquish parental rights"~5 OR "parental rights relinquish"~5 OR '
    '  "relinquished parental rights"~5 OR "parental rights relinquished"~5) OR '
    ' "Permanency hearing" OR "Legal guardianship" OR '
    ' "court-appointed special advocate" OR "guardian ad litem" OR '
    ' "out-of-home care" OR '
    ' ("foster care child"~20 OR "child foster care"~20 OR '
    '  "foster care children"~20 OR "children foster care"~20) OR '
    ' ("foster home child"~20 OR "child foster home"~20 OR '
    '  "foster home children"~20 OR "children foster home"~20) OR '
    ' ("foster parent child"~20 OR "child foster parent"~20 OR '
    '  "foster parent children"~20 OR "children foster parent"~20) OR '
    ' ("temporary placement child"~10 OR "child temporary placement"~10 OR '
    '  "temporary placement children"~10 OR "children temporary placement"~10) OR '
    ' "Kinship foster care" OR "kinship care" OR '
    ' "Permanency goal" OR "family reunification" OR "adoption assistance" OR '
    ' "parenting program" OR "Wraparound services" OR '
    ' "family preservation" OR "early childhood intervention" OR '
    ' "child care assistance" OR '
    ' ("mandated reporter child"~5 OR "child mandated reporter"~5 OR '
    '  "mandated reporter children"~5 OR "children mandated reporter"~5) OR '
    ' ("failure to report child"~5 OR "child failure to report"~5 OR '
    '  "failure to report children"~5 OR "children failure to report"~5) OR '
    ' "shaken baby syndrome" OR "abusive head trauma" OR '
    ' "parental substance use" )'
)

RATE_LIMIT_DELAY = 0.3
RATE_LIMIT_BACKOFF = 10
MAX_RETRIES = 3

# Year slices to stay under Overton's 1000-page (50K doc) API limit
YEAR_SLICES = [
    ("2023-01-01", "2023-12-31"),
    ("2024-01-01", "2024-12-31"),
    ("2025-01-01", "2025-12-31"),
]


def make_params(published_after, published_before):
    return {
        "api_key": API_KEY,
        "format": "json",
        "query": QUERY,
        "sector": "public_sector",
        "source_type": "government",
        "country": "USA",
        "published_after": published_after,
        "published_before": published_before,
        "sort": "published_on",
        "per_page": 50,
    }


def fetch_page(params, page):
    """Fetch a single page of results with retry logic."""
    req_params = {**params, "page": page}
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(DOCUMENTS_URL, params=req_params, timeout=30)
            if response.status_code == 429:
                wait = RATE_LIMIT_BACKOFF * (attempt + 1)
                print(f"    Rate limited. Waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            raise
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * (attempt + 1)
                print(f"    Request error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    return None


def fetch_year_slice(published_after, published_before):
    """Fetch all documents for a single year slice."""
    params = make_params(published_after, published_before)
    year_label = published_after[:4]

    # Checkpoint for this year slice
    cp_file = os.path.join(OUTPUT_DIR, f"checkpoint_{year_label}.json")

    # Check for existing checkpoint
    start_page = 1
    year_results = []
    if os.path.exists(cp_file):
        with open(cp_file, "r", encoding="utf-8") as f:
            cp = json.load(f)
        start_page = cp["last_page"] + 1
        year_results = cp["results"]
        total_results = cp["total_results"]
        total_pages = cp["total_pages"]
        print(f"  Resuming {year_label} from page {start_page}/{total_pages} "
              f"({len(year_results):,} docs already fetched)")
    else:
        # First page to get totals
        print(f"  Fetching {year_label} page 1...")
        data = fetch_page(params, 1)
        if data is None:
            print(f"  Failed to fetch {year_label} page 1. Skipping.")
            return []

        query_info = data.get("query", {})
        total_results = query_info.get("total_results", 0)
        total_pages = math.ceil(total_results / 50) if total_results > 0 else 0

        print(f"  {year_label}: {total_results:,} results, {total_pages} pages")

        if total_results == 0:
            return []

        results = data.get("results", [])
        if isinstance(results, dict):
            results = list(results.values())
        year_results = results
        start_page = 2

    # Fetch remaining pages
    for page in range(start_page, total_pages + 1):
        time.sleep(RATE_LIMIT_DELAY)
        try:
            data = fetch_page(params, page)
            if data is None:
                print(f"  Failed page {page}. Saving checkpoint...")
                with open(cp_file, "w", encoding="utf-8") as f:
                    json.dump({"last_page": page - 1, "total_results": total_results,
                               "total_pages": total_pages, "results": year_results}, f, ensure_ascii=False)
                return year_results

            results = data.get("results", [])
            if isinstance(results, dict):
                results = list(results.values())
            year_results.extend(results)

            if page % 50 == 0 or page == total_pages:
                print(f"  {year_label} page {page}/{total_pages}: {len(year_results):,} docs")

            # Checkpoint every 100 pages
            if page % 100 == 0:
                with open(cp_file, "w", encoding="utf-8") as f:
                    json.dump({"last_page": page, "total_results": total_results,
                               "total_pages": total_pages, "results": year_results}, f, ensure_ascii=False)

        except Exception as e:
            print(f"  Error on {year_label} page {page}: {e}")
            with open(cp_file, "w", encoding="utf-8") as f:
                json.dump({"last_page": page - 1, "total_results": total_results,
                           "total_pages": total_pages, "results": year_results}, f, ensure_ascii=False)
            print(f"  Checkpoint saved. Re-run to resume.")
            return year_results

    # Done with this year — clean up checkpoint
    if os.path.exists(cp_file):
        os.remove(cp_file)

    print(f"  {year_label} complete: {len(year_results):,} documents")
    return year_results


def matches_state_source(doc):
    """Check if a document's source matches one of the 49 state/commonwealth sources."""
    source = doc.get("source", {})
    if not isinstance(source, dict):
        return False
    source_title = (source.get("title") or "").lower()
    return source_title in STATE_SOURCES_LOWER


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Overton Policy Document Pull — US State Child Welfare")
    print("=" * 60)
    print(f"Sector:       Public sector")
    print(f"Org type:     Government")
    print(f"Country:      USA")
    print(f"Sources:      49 states/commonwealths")
    print(f"Date range:   2023-01-01 to 2025-12-31")
    print(f"Query:        Child welfare boolean search")
    print(f"Strategy:     Split by year (avoids 1000-page API limit)")
    print(f"Output:       {OUTPUT_FILE}")
    print("=" * 60)

    # Fetch each year slice
    all_results = []
    for pub_after, pub_before in YEAR_SLICES:
        year_label = pub_after[:4]
        print(f"\n--- Year {year_label} ---")
        year_docs = fetch_year_slice(pub_after, pub_before)
        all_results.extend(year_docs)
        print(f"Running total: {len(all_results):,} documents")

    print(f"\n{'=' * 60}")
    print(f"Total documents from API: {len(all_results):,}")

    # Deduplicate by policy_document_id
    seen_ids = set()
    deduped = []
    for doc in all_results:
        doc_id = doc.get("policy_document_id", "")
        if doc_id and doc_id not in seen_ids:
            seen_ids.add(doc_id)
            deduped.append(doc)
        elif not doc_id:
            deduped.append(doc)
    if len(deduped) < len(all_results):
        print(f"After dedup: {len(deduped):,} (removed {len(all_results) - len(deduped):,} duplicates)")
    all_results = deduped

    # Filter to 49 state sources
    print(f"\nFiltering to 49 state/commonwealth sources...")
    matched = [doc for doc in all_results if matches_state_source(doc)]
    unmatched_sources = {}
    for doc in all_results:
        if not matches_state_source(doc):
            source = doc.get("source", {})
            if isinstance(source, dict):
                title = source.get("title", "Unknown")
                unmatched_sources[title] = unmatched_sources.get(title, 0) + 1

    print(f"Documents matching state sources: {len(matched):,}")
    print(f"Documents from other sources:     {len(all_results) - len(matched):,}")

    if unmatched_sources:
        print(f"\nOther source orgs ({len(unmatched_sources)}):")
        for src, count in sorted(unmatched_sources.items(), key=lambda x: -x[1])[:20]:
            print(f"  - {src} ({count:,})")
        if len(unmatched_sources) > 20:
            print(f"  ... and {len(unmatched_sources) - 20} more")

    # State-level breakdown
    state_counts = {}
    for doc in matched:
        src = doc.get("source", {}).get("title", "Unknown")
        state_counts[src] = state_counts.get(src, 0) + 1

    print(f"\nDocuments per state:")
    for state in sorted(state_counts.keys()):
        print(f"  {state}: {state_counts[state]:,}")

    missing = [s for s in STATE_SOURCES if s.lower() not in
               {doc.get("source", {}).get("title", "").lower() for doc in matched}]
    if missing:
        print(f"\nStates with 0 documents: {', '.join(missing)}")

    # Save filtered results (49 states only)
    output = {
        "query_info": {
            "total_results_from_api": len(all_results),
            "documents_after_source_filter": len(matched),
            "filters": {
                "sector": "public_sector",
                "source_type": "government",
                "country": "USA",
                "published_after": "2023-01-01",
                "published_before": "2025-12-31",
                "sources": STATE_SOURCES,
            },
            "query_terms": "Child welfare boolean search (see claudeinfo.txt)",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "state_counts": state_counts,
        },
        "results": matched,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(matched):,} state-filtered documents to {OUTPUT_FILE}")

    # Also save full unfiltered set
    full_file = OUTPUT_FILE.replace(".json", "_all_usa_gov.json")
    full_output = {
        "query_info": {
            "total_results_from_api": len(all_results),
            "filters": {
                "sector": "public_sector",
                "source_type": "government",
                "country": "USA",
                "published_after": "2023-01-01",
                "published_before": "2025-12-31",
            },
            "query_terms": "Child welfare boolean search (see claudeinfo.txt)",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "results": all_results,
    }
    with open(full_file, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(all_results):,} documents (all USA gov) to {full_file}")

    # Clean up old checkpoint
    old_cp = os.path.join(OUTPUT_DIR, "us_gov_child_welfare_checkpoint.json")
    if os.path.exists(old_cp):
        os.remove(old_cp)
        print("Old checkpoint removed.")

    print("\nDone!")


if __name__ == "__main__":
    main()
