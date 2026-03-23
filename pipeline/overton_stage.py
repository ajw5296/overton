"""Stage 3: Enrich researchers with Overton policy document citations.

Queries the Overton API by ORCID for each researcher.
"""

import logging
from tqdm import tqdm

from . import config
from .utils import api_request, load_json, save_json, now_iso, days_since

logger = logging.getLogger("pipeline.overton")


def _fetch_overton(orcid: str) -> dict | None:
    """Query Overton for policy documents citing a researcher's work."""
    params = {
        "api_key": config.OVERTON_API_KEY,
        "format": "json",
        "query": orcid,
        "sort": "relevance",
    }

    # Query documents (policy) endpoint
    data = api_request(
        config.OVERTON_DOCUMENTS_URL,
        params=params,
        delay=config.OVERTON_DELAY,
        timeout=15,
    )
    if not data:
        return None

    total = data.get("query", {}).get("total_results", 0)
    if total == 0:
        return None

    # Parse policy documents
    policy_docs = []
    for doc in data.get("results", []):
        source = doc.get("source", {})
        policy_docs.append({
            "policy_document_id": doc.get("policy_document_id", ""),
            "title": doc.get("title"),
            "source": {
                "title": source.get("title"),
                "country": source.get("country"),
                "type": source.get("type"),
                "organisation_type": source.get("organisation_type"),
            },
            "published_on": doc.get("published_on"),
            "topics": doc.get("topics", []),
            "sdgcategories": doc.get("sdgcategories", []),
            "overton_url": doc.get("overton_url"),
        })

    return {
        "policy_documents_total": total,
        "policy_documents": policy_docs,
        "last_fetched": now_iso(),
    }


def run(researchers: list[dict], incremental: bool = False,
        skip_no_hits: bool = False) -> list[dict]:
    """Enrich researchers with Overton policy document data.

    Args:
        researchers: List of researcher dicts from Stage 2.
        incremental: Skip researchers already enriched within INCREMENTAL_SKIP_DAYS.
        skip_no_hits: Skip ORCIDs that previously had zero hits.

    Returns:
        Updated list of researcher dicts with overton field populated.
    """
    output_path = config.DATA_DIR / config.OVERTON_OUTPUT

    # Load previous no-hits list for skip_no_hits mode
    no_hits_path = config.DATA_DIR / "overton_no_hits.json"
    no_hits_set = set(load_json(no_hits_path, [])) if skip_no_hits else set()

    enriched = 0
    skipped = 0
    new_no_hits = []

    print(f"Overton: Processing {len(researchers)} researchers...")
    if skip_no_hits and no_hits_set:
        print(f"Overton: Skipping {len(no_hits_set)} known no-hit ORCIDs")

    for researcher in tqdm(researchers, desc="Overton enrichment"):
        orcid = researcher["orcid"]

        # Incremental: skip if recently fetched
        if incremental and researcher.get("overton") is not None:
            ov_fetched = (researcher.get("overton") or {}).get("last_fetched")
            if ov_fetched and days_since(ov_fetched) < config.INCREMENTAL_SKIP_DAYS:
                skipped += 1
                continue

        # Skip known no-hits
        if skip_no_hits and orcid in no_hits_set:
            if researcher.get("overton") is None:
                researcher["overton"] = {"policy_documents_total": 0,
                                          "policy_documents": [],
                                          "last_fetched": now_iso()}
            skipped += 1
            continue

        result = _fetch_overton(orcid)
        if result:
            researcher["overton"] = result
            enriched += 1
        else:
            researcher["overton"] = {
                "policy_documents_total": 0,
                "policy_documents": [],
                "last_fetched": now_iso(),
            }
            new_no_hits.append(orcid)

    # Update no-hits list
    all_no_hits = sorted(set(list(no_hits_set) + new_no_hits))
    save_json(all_no_hits, no_hits_path)

    print(f"Overton: {enriched} with policy docs, {len(new_no_hits)} new no-hits, {skipped} skipped")
    save_json(researchers, output_path, compact=True)
    return researchers
