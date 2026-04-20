"""Stage 1: Load HHD researcher cohort from RMD.

Loads the cached ORCID→WebAccess ID map from S3, then fetches full RMD
profiles (grants, presentations, ETDs, org memberships) for each researcher.
Creates the initial researcher records in the database.

The ORCID map is built once via --rebuild-map and cached in S3 at
pipeline-cache/orcid_webaccess_map.json. Subsequent runs just load it.
"""

import logging
from tqdm import tqdm

from . import config
from .utils import api_request, load_json, save_json, now_iso, days_since
from .db.operations import upsert_researcher, get_all_researchers
from .db.s3_client import (
    upload_raw_response,
    load_json_from_s3,
    save_json_to_s3,
)

logger = logging.getLogger("pipeline.rmd")

S3_MAP_KEY = "pipeline-cache/orcid_webaccess_map.json"

RMD_HEADERS = {
    "X-API-Key": config.RMD_API_KEY,
    "Accept": "application/json",
}
RMD_PUBLIC_HEADERS = {"Accept": "application/json"}


def _load_orcid_map() -> dict[str, str]:
    """Load the ORCID→WebAccess ID map from S3, falling back to local file."""
    orcid_map = None
    try:
        orcid_map = load_json_from_s3(S3_MAP_KEY)
        if orcid_map:
            logger.info("Loaded %d ORCID mappings from S3", len(orcid_map))
    except Exception as e:
        logger.warning("Failed to load ORCID map from S3: %s", e)

    if not orcid_map:
        map_path = config.DATA_DIR / config.ORCID_WEBACCESS_MAP
        orcid_map = load_json(map_path, {})
        if orcid_map:
            logger.info("Loaded %d ORCID mappings from local file", len(orcid_map))

    return orcid_map or {}


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
        try:
            upload_raw_response("rmd", f"profile_{webaccess_id}", profile_data)
        except Exception as e:
            logger.warning("Failed to archive profile to S3: %s", e)

    # Grants
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

    # Presentations count
    pres_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/presentations",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if pres_data:
        result["presentations_count"] = len(pres_data.get("data", []))

    # ETDs count
    etds_data = api_request(
        f"{config.RMD_BASE_URL}/users/{webaccess_id}/etds",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if etds_data:
        result["etds_count"] = len(etds_data.get("data", []))

    # Organization memberships
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


def _normalize_doi(doi: str) -> str:
    """Normalize a DOI to bare form (no URL prefix, lowercase)."""
    return doi.lower().strip().replace("https://doi.org/", "").replace("http://doi.org/", "")


def _scan_rmd_publications() -> tuple[dict[str, set[str]], dict[str, str]]:
    """Scan all HHD org publications and extract user info.

    Returns:
        (user_dois, user_names): mappings from psu_user_id to DOIs and display names.
    """
    print("RMD: Fetching organizations...")
    orgs_data = api_request(
        f"{config.RMD_BASE_URL}/organizations",
        headers=RMD_HEADERS,
        delay=config.RMD_DELAY,
    )
    if not orgs_data:
        logger.error("Failed to fetch RMD organizations")
        return {}, {}

    orgs = orgs_data.get("data", [])
    print(f"RMD: Found {len(orgs)} organizations")

    user_dois = {}   # psu_user_id -> set of DOIs
    user_names = {}  # psu_user_id -> "First Last"

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
                    if not uid:
                        continue
                    # Collect name
                    if uid not in user_names:
                        first = (contrib.get("first_name") or "").strip()
                        last = (contrib.get("last_name") or "").strip()
                        if first and last:
                            user_names[uid] = f"{first} {last}"
                    # Collect DOI
                    if doi:
                        user_dois.setdefault(uid, set()).add(_normalize_doi(doi))
                    # Check for ORCID directly on contributor record
                    contrib_orcid = contrib.get("orcid")
                    if contrib_orcid:
                        contrib_orcid = contrib_orcid.replace("https://orcid.org/", "").strip()
                        if contrib_orcid:
                            # Store as a special DOI-like marker so we pick it up
                            user_dois.setdefault(uid, set())
                            user_names.setdefault(uid, f"{contrib.get('first_name', '')} {contrib.get('last_name', '')}")
            if len(pubs) < limit:
                break
            offset += limit

    print(f"RMD: Found {len(user_dois)} unique users, "
          f"{sum(len(d) for d in user_dois.values())} total DOIs")
    return user_dois, user_names


def _fetch_openalex_doi_to_orcid() -> dict[str, set[str]]:
    """Fetch all PSU authors from OpenAlex and build DOI→ORCID mappings.

    Uses the works endpoint for each author to get their DOIs, but more
    efficiently: fetches authors with their works_api_url, then queries
    works by institution to build a DOI→ORCIDs index.

    Returns:
        doi_to_orcids: mapping from normalized DOI to set of ORCIDs.
    """
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}
    filter_param = f"affiliations.institution.ror:{config.PSU_ROR},has_orcid:true"
    select_fields = "id,orcid,display_name"

    # Step 1: Collect all PSU ORCIDs and names
    print("OpenAlex: Fetching all PSU authors with ORCIDs...")
    orcid_to_name = {}
    cursor = "*"
    page = 0

    while True:
        data = api_request(
            f"{config.OPENALEX_BASE_URL}/authors",
            params={
                "filter": filter_param,
                "per_page": 200,
                "cursor": cursor,
                "select": select_fields,
            },
            headers=headers,
            delay=config.OPENALEX_DELAY,
        )
        if not data:
            break

        results = data.get("results", [])
        if not results:
            break

        for author in results:
            orcid_raw = author.get("orcid")
            if not orcid_raw:
                continue
            orcid = orcid_raw.replace("https://orcid.org/", "")
            name = author.get("display_name", "")
            orcid_to_name[orcid] = name

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        page += 1
        if page % 50 == 0:
            print(f"  ...fetched {len(orcid_to_name):,} authors")

    print(f"OpenAlex: {len(orcid_to_name):,} PSU authors with ORCIDs")
    return orcid_to_name


def _match_by_doi(rmd_user_dois: dict[str, set[str]], rmd_user_names: dict[str, str],
                  orcid_to_name: dict[str, str]) -> dict[str, str]:
    """Match RMD users to OpenAlex ORCIDs by looking up shared DOIs.

    For each unmapped RMD user, takes their DOIs, queries OpenAlex for
    the authors of those works, and matches by name.

    Returns:
        New ORCID→WebAccess mappings found via DOI cross-reference.
    """
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}
    new_mappings = {}

    # Build a name→orcid lookup for quick matching (lowercase for fuzzy)
    name_to_orcid = {}
    for orcid, name in orcid_to_name.items():
        normalized = name.lower().strip()
        # Store all ORCIDs for a given name (handle duplicates)
        name_to_orcid.setdefault(normalized, []).append(orcid)

    users_to_check = [(uid, dois) for uid, dois in rmd_user_dois.items() if dois]
    print(f"DOI cross-ref: Checking {len(users_to_check)} RMD users against OpenAlex...")

    for uid, dois in tqdm(users_to_check, desc="DOI cross-reference"):
        rmd_name = rmd_user_names.get(uid, "").lower().strip()
        if not rmd_name:
            continue

        # Strategy 1: Quick name match against all PSU ORCIDs
        if rmd_name in name_to_orcid:
            orcid = name_to_orcid[rmd_name][0]
            new_mappings[orcid] = uid
            continue

        # Strategy 2: Look up a sample DOI in OpenAlex to find authors
        sample_dois = list(dois)[:3]
        matched = False
        for doi in sample_dois:
            work_data = api_request(
                f"{config.OPENALEX_BASE_URL}/works/doi:{doi}",
                headers=headers,
                delay=config.OPENALEX_DELAY,
            )
            if not work_data:
                continue

            # Check each authorship for name match
            for authorship in work_data.get("authorships", []):
                author = authorship.get("author", {})
                orcid_raw = author.get("orcid")
                if not orcid_raw:
                    continue
                orcid = orcid_raw.replace("https://orcid.org/", "")
                oa_name = (author.get("display_name") or "").lower().strip()

                # Match by name on shared publication
                if _names_match(rmd_name, oa_name):
                    new_mappings[orcid] = uid
                    matched = True
                    break
            if matched:
                break

    return new_mappings


def _names_match(name_a: str, name_b: str) -> bool:
    """Check if two names likely refer to the same person.

    Handles variations like "John A. Smith" vs "John Smith" and
    initial-based differences.
    """
    if not name_a or not name_b:
        return False

    # Exact match
    if name_a == name_b:
        return True

    # Split into parts, remove middle initials and periods
    def _normalize_parts(name):
        parts = name.replace(".", "").replace(",", "").split()
        # Filter out single-letter initials
        return [p for p in parts if len(p) > 1]

    parts_a = _normalize_parts(name_a)
    parts_b = _normalize_parts(name_b)

    if len(parts_a) < 2 or len(parts_b) < 2:
        return False

    # First and last name match (ignoring middle names/initials)
    return parts_a[0] == parts_b[0] and parts_a[-1] == parts_b[-1]


def rebuild_orcid_map() -> dict[str, str]:
    """Rebuild the ORCID→WebAccess map using three strategies:

    1. ORCID directly on RMD publication contributor records
    2. Name matching against all PSU OpenAlex authors
    3. DOI cross-reference: look up shared publications in OpenAlex
    4. Fallback: RMD profile orcid_identifier field

    Run via: python -m pipeline.run --rebuild-map
    """
    orcid_map = _load_orcid_map()
    existing_uids = set(orcid_map.values())
    print(f"Starting with {len(orcid_map)} existing mappings")

    # Step 1: Scan RMD publications for user IDs, DOIs, and names
    user_dois, user_names = _scan_rmd_publications()

    # Step 2: Fetch all PSU ORCIDs from OpenAlex
    orcid_to_name = _fetch_openalex_doi_to_orcid()

    # Step 3: Match by name first (fast, no API calls)
    name_to_orcid = {}
    for orcid, name in orcid_to_name.items():
        normalized = name.lower().strip()
        name_to_orcid.setdefault(normalized, []).append(orcid)

    name_matched = 0
    unmapped_after_name = []
    for uid in user_dois:
        if uid in existing_uids:
            continue
        rmd_name = user_names.get(uid, "").lower().strip()
        if rmd_name and rmd_name in name_to_orcid:
            orcid = name_to_orcid[rmd_name][0]
            if orcid not in orcid_map:
                orcid_map[orcid] = uid
                existing_uids.add(uid)
                name_matched += 1
        else:
            unmapped_after_name.append(uid)

    print(f"Name matching: {name_matched} new mappings")
    print(f"Still unmapped: {len(unmapped_after_name)} users")

    # Step 4: DOI cross-reference for remaining unmapped users
    unmapped_user_dois = {uid: user_dois[uid] for uid in unmapped_after_name if user_dois.get(uid)}
    doi_mappings = _match_by_doi(unmapped_user_dois, user_names, orcid_to_name)

    doi_matched = 0
    for orcid, uid in doi_mappings.items():
        if orcid not in orcid_map and uid not in existing_uids:
            orcid_map[orcid] = uid
            existing_uids.add(uid)
            doi_matched += 1

    print(f"DOI cross-reference: {doi_matched} new mappings")

    # Step 5: Profile lookup fallback for still-unmapped users
    still_unmapped = [uid for uid in unmapped_after_name
                      if uid not in existing_uids and uid not in doi_mappings.values()]
    print(f"Profile fallback: checking {len(still_unmapped)} remaining users...")

    profile_matched = 0
    for uid in tqdm(still_unmapped, desc="RMD profile ORCID lookup"):
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
            orcid = orcid.replace("https://orcid.org/", "").strip()
            if orcid and orcid not in orcid_map:
                orcid_map[orcid] = uid
                existing_uids.add(uid)
                profile_matched += 1

    print(f"Profile lookup: {profile_matched} new mappings")

    # Save to S3 and local
    try:
        save_json_to_s3(S3_MAP_KEY, orcid_map)
    except Exception as e:
        logger.warning("Failed to save ORCID map to S3: %s", e)
    map_path = config.DATA_DIR / config.ORCID_WEBACCESS_MAP
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(orcid_map, map_path)

    print(f"\n=== ORCID Map Summary ===")
    print(f"  Total mappings: {len(orcid_map)}")
    print(f"  New from name match: {name_matched}")
    print(f"  New from DOI cross-ref: {doi_matched}")
    print(f"  New from profile lookup: {profile_matched}")
    print(f"  Previously existing: {len(orcid_map) - name_matched - doi_matched - profile_matched}")
    return orcid_map


def run(max_researchers: int | None = None,
        incremental: bool = False) -> dict:
    """Load HHD researcher cohort from cached ORCID map and fetch RMD profiles.

    Args:
        max_researchers: Limit number of researchers (for testing).
        incremental: Skip researchers fetched within INCREMENTAL_SKIP_DAYS.

    Returns:
        Stats dict with counts.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    orcid_map = _load_orcid_map()
    if not orcid_map:
        print("ERROR: No ORCID map found. Run with --rebuild-map first.")
        return {"error": "no ORCID map", "fetched": 0}

    researchers_to_process = list(orcid_map.items())
    if max_researchers:
        researchers_to_process = researchers_to_process[:max_researchers]

    print(f"RMD: {len(researchers_to_process)} researchers in cohort"
          f" (from {len(orcid_map)} total in map)")

    # Load existing researchers for incremental check
    existing = {}
    if incremental:
        try:
            for r in get_all_researchers():
                existing[r["orcid"]] = r["data"]
        except Exception:
            pass

    fetched = 0
    skipped = 0

    for orcid, webaccess_id in tqdm(researchers_to_process, desc="RMD cohort"):
        # Incremental: skip if recently fetched
        if incremental and orcid in existing:
            rmd_data = existing[orcid].get("rmd") or {}
            last_fetched = rmd_data.get("last_fetched")
            if last_fetched and days_since(last_fetched) < config.INCREMENTAL_SKIP_DAYS:
                skipped += 1
                continue

        rmd_data = _fetch_rmd_data(webaccess_id)
        display_name = (rmd_data.get("profile") or {}).get("title") or webaccess_id

        researcher = {
            "orcid": orcid,
            "openalex_id": None,
            "display_name": display_name,
            "openalex": None,
            "rmd": rmd_data,
            "overton": None,
        }

        try:
            upsert_researcher(researcher)
            fetched += 1
        except Exception as e:
            logger.warning("Failed to upsert researcher %s: %s", orcid, e)

    stats = {
        "total_in_map": len(orcid_map),
        "fetched": fetched,
        "skipped": skipped,
    }
    print(f"RMD: Fetched {fetched}, skipped {skipped}")
    return stats
