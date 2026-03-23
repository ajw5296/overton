"""Stage 2: Enrich researchers with PSU RMD (Researcher Metadata Database) data.

Resolution strategy:
1. Fetch all publications from HHD orgs, extract psu_user_id + DOI pairs
2. Cross-reference DOIs with OpenAlex ORCIDs to build ORCID->WebAccess mapping
3. For mapped researchers: fetch profile (public), grants, presentations, ETDs
"""

import logging
import time
from tqdm import tqdm

from . import config
from .utils import api_request, load_json, save_json, now_iso, days_since

logger = logging.getLogger("pipeline.rmd")

RMD_HEADERS = {
    "X-API-Key": config.RMD_API_KEY,
    "Accept": "application/json",
}
RMD_PUBLIC_HEADERS = {"Accept": "application/json"}


def _build_orcid_webaccess_map(researchers: list[dict]) -> dict[str, str]:
    """Build ORCID->WebAccess ID mapping by cross-referencing RMD org publications.

    Fetches all publications from HHD organizations, extracts (psu_user_id, DOI) pairs,
    then matches DOIs against OpenAlex researcher ORCIDs.
    """
    map_path = config.DATA_DIR / config.ORCID_WEBACCESS_MAP
    orcid_map = load_json(map_path, {})
    if orcid_map:
        logger.info(f"Loaded {len(orcid_map)} cached ORCID->WebAccess mappings")

    # Build DOI->ORCID lookup from our researchers
    doi_to_orcid = {}
    # We don't have DOIs directly in the researcher record yet.
    # Instead we'll use the RMD profile's orcid_identifier field for matching.

    # Step 1: Get all RMD organizations
    print("RMD: Fetching organizations for ORCID mapping...")
    orgs_data = api_request(
        f"{config.RMD_BASE_URL}/organizations",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if not orgs_data:
        logger.warning("Failed to fetch RMD organizations")
        return orcid_map

    orgs = orgs_data.get("data", [])
    logger.info(f"Found {len(orgs)} RMD organizations")

    # Step 2: Fetch publications from each org, extract psu_user_ids
    all_psu_user_ids = set()
    user_dois = {}  # psu_user_id -> set of DOIs

    for org in tqdm(orgs, desc="RMD org publications"):
        org_id = org["id"]
        offset = 0
        limit = 100

        while True:
            data = api_request(
                f"{config.RMD_BASE_URL}/organizations/{org_id}/publications",
                params={"limit": limit, "offset": offset},
                headers=RMD_HEADERS,
                delay=config.RMD_DELAY,
            )
            if not data:
                break

            pubs = data.get("data", [])
            if not pubs:
                break

            for pub in pubs:
                attrs = pub.get("attributes", {})
                doi = attrs.get("doi")
                for contrib in attrs.get("contributors", []):
                    uid = contrib.get("psu_user_id")
                    if uid:
                        all_psu_user_ids.add(uid)
                        if doi:
                            user_dois.setdefault(uid, set()).add(doi)

            if len(pubs) < limit:
                break
            offset += limit

    print(f"RMD: Found {len(all_psu_user_ids)} unique PSU user IDs from HHD publications")

    # Step 3: For each user ID not already mapped, try profile lookup for ORCID
    unmapped_users = [uid for uid in all_psu_user_ids if uid not in set(orcid_map.values())]
    if unmapped_users:
        print(f"RMD: Resolving ORCIDs for {len(unmapped_users)} unmapped users...")
        for uid in tqdm(unmapped_users, desc="RMD profile ORCID lookup"):
            profile_data = api_request(
                f"{config.RMD_BASE_URL}/users/{uid}/profile",
                headers=RMD_PUBLIC_HEADERS,
                delay=config.RMD_DELAY,
            )
            if not profile_data:
                continue
            attrs = (profile_data.get("data") or {}).get("attributes", {})
            orcid = attrs.get("orcid_identifier")
            if orcid:
                orcid = orcid.replace("https://orcid.org/", "")
                orcid_map[orcid] = uid

    # Save the map
    save_json(orcid_map, map_path)
    print(f"RMD: ORCID->WebAccess map has {len(orcid_map)} entries")
    return orcid_map


def _fetch_rmd_data(webaccess_id: str) -> dict:
    """Fetch all RMD data for a researcher by WebAccess ID."""
    result = {
        "webaccess_id": webaccess_id,
        "profile": {},
        "grants": [],
        "presentations_count": 0,
        "etds_count": 0,
        "org_memberships": [],
        "last_fetched": now_iso(),
    }

    # Profile (public endpoint)
    profile_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/profile",
        headers=RMD_PUBLIC_HEADERS,
        delay=config.RMD_DELAY,
    )
    if profile_data:
        attrs = (profile_data.get("data") or {}).get("attributes", {})
        result["profile"] = {
            "title": attrs.get("title"),
            "organization_name": attrs.get("organization_name"),
            "email": attrs.get("email"),
            "total_scopus_citations": attrs.get("total_scopus_citations"),
            "scopus_h_index": attrs.get("scopus_h_index"),
            "bio": attrs.get("bio"),
            "pure_profile_url": attrs.get("pure_profile_url"),
        }

    # Grants (auth required - HHD only)
    grants_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/grants",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if grants_data:
        for g in grants_data.get("data", []):
            attrs = g.get("attributes", {})
            result["grants"].append({
                "id": str(g.get("id", "")),
                "title": attrs.get("title"),
                "agency": attrs.get("agency"),
                "amount_in_dollars": attrs.get("amount_in_dollars"),
                "start_date": attrs.get("start_date"),
                "end_date": attrs.get("end_date"),
            })

    # Presentations count (auth required)
    pres_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/presentations",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if pres_data:
        result["presentations_count"] = len(pres_data.get("data", []))

    # ETDs count (auth required)
    etds_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/etds",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if etds_data:
        result["etds_count"] = len(etds_data.get("data", []))

    # Organization memberships (auth required)
    orgs_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/organization_memberships",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if orgs_data:
        for m in orgs_data.get("data", []):
            attrs = m.get("attributes", {})
            result["org_memberships"].append({
                "organization_name": attrs.get("organization_name"),
                "organization_type": attrs.get("organization_type"),
                "position_title": attrs.get("position_title"),
            })

    return result


def run(researchers: list[dict], incremental: bool = False) -> list[dict]:
    """Enrich researchers with RMD data.

    Args:
        researchers: List of researcher dicts from Stage 1.
        incremental: Skip researchers already enriched within INCREMENTAL_SKIP_DAYS.

    Returns:
        Updated list of researcher dicts with rmd field populated where possible.
    """
    output_path = config.DATA_DIR / config.RMD_OUTPUT

    # Build ORCID->WebAccess mapping
    orcid_map = _build_orcid_webaccess_map(researchers)

    # Enrich each researcher
    matched = 0
    skipped = 0

    orcid_set = {r["orcid"] for r in researchers}
    mappable = {orcid for orcid in orcid_set if orcid in orcid_map}
    print(f"RMD: {len(mappable)} of {len(researchers)} researchers have WebAccess IDs")

    for researcher in tqdm(researchers, desc="RMD enrichment"):
        orcid = researcher["orcid"]

        # Incremental: skip if recently fetched
        if incremental and researcher.get("rmd"):
            rmd_fetched = researcher["rmd"].get("last_fetched")
            if rmd_fetched and days_since(rmd_fetched) < config.INCREMENTAL_SKIP_DAYS:
                skipped += 1
                continue

        webaccess_id = orcid_map.get(orcid)
        if not webaccess_id:
            # Not in RMD - mark as attempted but empty
            researcher["rmd"] = {"webaccess_id": None, "last_fetched": now_iso()}
            continue

        researcher["rmd"] = _fetch_rmd_data(webaccess_id)
        matched += 1

    print(f"RMD: Enriched {matched}, skipped {skipped} (incremental)")
    save_json(researchers, output_path)
    return researchers
