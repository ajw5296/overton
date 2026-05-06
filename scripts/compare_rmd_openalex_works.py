"""Compare the completeness of a researcher's works between RMD and OpenAlex.

For a sample of the 750 already-mapped PSU researchers (we have both the
ORCID and the WebAccess ID), pulls the full DOI list from each source and
compares:

  - RMD: paginated GET /users/{uid}/publications
  - OpenAlex: paginated GET /works?filter=author.orcid:<orcid>

Reports per-researcher: |RMD|, |OpenAlex|, |both|, RMD-only, OA-only.
Prints aggregate coverage statistics.

Run: python -m scripts.compare_rmd_openalex_works
"""

import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import config
from pipeline.utils import load_json, save_json

SAMPLE_SIZE = 20
MAX_PAGES = 20  # safety cap on pagination


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return (
        doi.lower()
        .strip()
        .replace("https://doi.org/", "")
        .replace("http://doi.org/", "")
        .rstrip(".")
    )


def _rmd_dois(uid: str) -> tuple[set[str], int] | None:
    """Return (normalized DOI set, count of records) or None on 404."""
    dois: set[str] = set()
    count = 0
    offset = 0
    limit = 100
    pages = 0
    while pages < MAX_PAGES:
        pages += 1
        url = f"{config.RMD_BASE_URL}/users/{uid}/publications?" + urllib.parse.urlencode(
            {"limit": limit, "offset": offset}
        )
        req = urllib.request.Request(
            url, headers={"X-API-Key": config.RMD_API_KEY, "Accept": "application/json"}
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        data = json.loads(resp.read())
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            count += 1
            d = _normalize_doi((row.get("attributes") or {}).get("doi"))
            if d:
                dois.add(d)
        if len(rows) < limit:
            break
        offset += limit
        time.sleep(0.3)
    return dois, count


def _openalex_dois(orcid: str) -> tuple[set[str], int]:
    """Return (normalized DOI set, total works count from OpenAlex)."""
    dois: set[str] = set()
    count = 0
    cursor = "*"
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}
    pages = 0
    while pages < MAX_PAGES:
        pages += 1
        url = f"{config.OPENALEX_BASE_URL}/works?" + urllib.parse.urlencode({
            "filter": f"author.orcid:{orcid}",
            "per-page": 200,
            "cursor": cursor,
            "select": "doi",
        })
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except Exception:
            break
        d = json.loads(resp.read())
        results = d.get("results") or []
        count += len(results)
        for w in results:
            norm = _normalize_doi(w.get("doi"))
            if norm:
                dois.add(norm)
        cursor = (d.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.1)
    return dois, count


def main() -> None:
    orcid_map = load_json(config.DATA_DIR / config.ORCID_WEBACCESS_MAP, {})
    if not orcid_map:
        print("No ORCID map")
        return
    random.seed(7)
    sample = random.sample(list(orcid_map.items()), min(SAMPLE_SIZE * 2, len(orcid_map)))

    rows = []
    out = config.DATA_DIR / "rmd_vs_openalex_works.json"
    for orcid, uid in tqdm(sample, desc="comparing works"):
        if len(rows) >= SAMPLE_SIZE:
            break
        rmd_result = _rmd_dois(uid)
        if rmd_result is None:
            continue  # skip 404 users
        rmd, rmd_total = rmd_result
        oa, oa_total = _openalex_dois(orcid)
        both = rmd & oa
        rmd_only = rmd - oa
        oa_only = oa - rmd
        rows.append({
            "orcid": orcid, "uid": uid,
            "rmd_records": rmd_total, "rmd_with_doi": len(rmd),
            "oa_records": oa_total,  "oa_with_doi":  len(oa),
            "both": len(both),
            "rmd_only": len(rmd_only),
            "oa_only": len(oa_only),
            "sample_rmd_only_dois": sorted(rmd_only)[:5],
            "sample_oa_only_dois":  sorted(oa_only)[:5],
        })
        save_json({"rows": rows}, out)  # incremental save

    n = len(rows)
    if not n:
        print("No researchers comparable (all 404s?)")
        return

    print(f"\n=== Sample: {n} mapped PSU researchers ===")
    print(f'{"orcid":<22} {"uid":<10} {"rmd":>5} {"oa":>5} {"both":>5} {"rmd-":>5} {"oa-":>5} {"% rmd":>6} {"% oa":>6}')
    for r in rows:
        rmd_cov = r["both"] / r["rmd_with_doi"] * 100 if r["rmd_with_doi"] else 0
        oa_cov  = r["both"] / r["oa_with_doi"]  * 100 if r["oa_with_doi"] else 0
        print(f'{r["orcid"]:<22} {r["uid"]:<10} {r["rmd_with_doi"]:>5} {r["oa_with_doi"]:>5} '
              f'{r["both"]:>5} {r["rmd_only"]:>5} {r["oa_only"]:>5} {rmd_cov:>5.0f}% {oa_cov:>5.0f}%')

    total_rmd = sum(r["rmd_with_doi"] for r in rows)
    total_oa  = sum(r["oa_with_doi"]  for r in rows)
    total_both = sum(r["both"] for r in rows)
    total_rmd_only = sum(r["rmd_only"] for r in rows)
    total_oa_only = sum(r["oa_only"] for r in rows)
    print(f"\n=== Aggregate (sum across sample) ===")
    print(f"  RMD DOIs total:         {total_rmd}")
    print(f"  OpenAlex DOIs total:    {total_oa}")
    print(f"  Present in both:        {total_both}")
    print(f"  RMD-only:               {total_rmd_only}  ({total_rmd_only/total_rmd*100:.0f}% of RMD)" if total_rmd else "  RMD total: 0")
    print(f"  OpenAlex-only:          {total_oa_only}  ({total_oa_only/total_oa*100:.0f}% of OpenAlex)" if total_oa else "  OA total: 0")
    print(f"\n  RMD coverage by OpenAlex:    {total_both/total_rmd*100:.0f}% of RMD DOIs are in OpenAlex" if total_rmd else "")
    print(f"  OpenAlex coverage by RMD:    {total_both/total_oa*100:.0f}% of OpenAlex DOIs are in RMD" if total_oa else "")

    # Show a few RMD-only DOIs to eyeball what OpenAlex is missing
    print(f"\n=== Sample RMD-only DOIs (might reveal what OpenAlex misses) ===")
    shown = 0
    for r in rows:
        if r["sample_rmd_only_dois"]:
            for d in r["sample_rmd_only_dois"][:2]:
                print(f"  {r['orcid']}  {d}")
                shown += 1
                if shown >= 10:
                    break
        if shown >= 10:
            break

    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
