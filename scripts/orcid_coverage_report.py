"""Diagnostic: measure ORCID coverage of the RMD researcher cohort.

Enumerates every unique psu_user_id that appears as a publication contributor
across all HHD organizations in RMD, then for each user NOT already in the
ORCID map, hits /users/{uid}/profile to see whether RMD has an
`orcid_identifier` recorded.

Answers: of the RMD users we can see, how many genuinely lack an ORCID in RMD
vs. how many have one we've failed to match to OpenAlex.

Run: python -m scripts.orcid_coverage_report
"""

import json
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import config
from pipeline.utils import api_request, save_json, load_json
from pipeline.rmd_stage import _scan_rmd_publications, RMD_PUBLIC_HEADERS


def _check_profile_orcid(uid: str) -> str | None:
    """Fetch RMD profile and return the orcid_identifier if set, else None."""
    data = api_request(
        f"{config.RMD_BASE_URL}/users/{uid}/profile",
        headers=RMD_PUBLIC_HEADERS,
        delay=config.RMD_DELAY,
    )
    if not data:
        return None
    attrs = (data.get("data") or {}).get("attributes", {})
    orcid = attrs.get("orcid_identifier")
    if not orcid:
        return None
    return orcid.replace("https://orcid.org/", "").strip() or None


def main() -> None:
    map_path = config.DATA_DIR / config.ORCID_WEBACCESS_MAP
    orcid_map = load_json(map_path, {})
    mapped_uids = set(orcid_map.values())
    print(f"Current ORCID map: {len(orcid_map)} entries ({len(mapped_uids)} unique uids)\n")

    user_dois, user_names = _scan_rmd_publications()
    all_uids = set(user_dois.keys())
    print(f"\nTotal unique psu_user_ids in RMD publications: {len(all_uids)}\n")

    unmapped = sorted(all_uids - mapped_uids)
    print(f"Checking {len(unmapped)} unmapped users' profiles for orcid_identifier...\n")

    has_orcid_in_profile = []  # [(uid, name, orcid)]
    no_orcid_in_profile = []   # [(uid, name)]
    profile_fetch_failed = []  # [(uid, name)]

    for uid in tqdm(unmapped, desc="profile lookups"):
        name = user_names.get(uid, "")
        try:
            orcid = _check_profile_orcid(uid)
        except Exception as e:
            profile_fetch_failed.append((uid, name))
            continue
        if orcid:
            has_orcid_in_profile.append((uid, name, orcid))
        else:
            no_orcid_in_profile.append((uid, name))

    total = len(all_uids)
    print("\n=== ORCID Coverage Report ===")
    print(f"Total RMD users (via publications):         {total}")
    print(f"  Already mapped to ORCID:                  {len(mapped_uids & all_uids)}")
    print(f"  Unmapped with ORCID in RMD profile:       {len(has_orcid_in_profile)}")
    print(f"  Unmapped, no ORCID in RMD profile:        {len(no_orcid_in_profile)}")
    print(f"  Profile fetch failed:                     {len(profile_fetch_failed)}")

    pct_any = (len(mapped_uids & all_uids) + len(has_orcid_in_profile)) / total * 100 if total else 0
    print(f"\n  % of RMD users with *any* ORCID known:   {pct_any:.1f}%")

    out = {
        "summary": {
            "total_rmd_users": total,
            "already_mapped": len(mapped_uids & all_uids),
            "unmapped_with_profile_orcid": len(has_orcid_in_profile),
            "unmapped_no_profile_orcid": len(no_orcid_in_profile),
            "profile_fetch_failed": len(profile_fetch_failed),
        },
        "unmapped_with_profile_orcid": [
            {"uid": u, "name": n, "orcid": o} for u, n, o in has_orcid_in_profile
        ],
        "unmapped_no_profile_orcid": [
            {"uid": u, "name": n} for u, n in no_orcid_in_profile
        ],
        "profile_fetch_failed": [
            {"uid": u, "name": n} for u, n in profile_fetch_failed
        ],
    }
    out_path = config.DATA_DIR / "orcid_coverage_report.json"
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(out, out_path)
    print(f"\nWrote detail to {out_path}")


if __name__ == "__main__":
    main()
