"""Test: which source (RMD or OpenAlex) gives a researcher's name in the
form that Overton's r_open_institution_authors filter recognizes?

Takes a sample of the 750 already-mapped PSU researchers (we have their
ORCIDs so we know their 'true' Overton article count). For each, fetches
their RMD `attributes.name` and their OpenAlex `display_name`, then queries
Overton three ways:

    1. baseline:  articles.php?query=<ORCID>
    2. RMD-name:  articles.php?r_open_institution_authors=<PSU_ROR>__OVSEP__<rmd_name>__OVSEP__<lower>
    3. OA-name:   articles.php?r_open_institution_authors=<PSU_ROR>__OVSEP__<oa_name>__OVSEP__<lower>

Compares the three counts and reports which name source recovers the
baseline article count more reliably.

Run: python -m scripts.compare_rmd_vs_openalex_names
"""

import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import config
from pipeline.utils import load_json, save_json

PSU_ROR = "https://ror.org/04p491231"
SAMPLE_SIZE = 40


def _ovget(endpoint: str, **params) -> dict:
    params["format"] = "json"
    params["api_key"] = config.OVERTON_API_KEY
    url = f"https://app.overton.io/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        resp = urllib.request.urlopen(url, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {"query": {"total_results": -1, "error": str(e)}}


def _rmd_name(webaccess_id: str) -> str:
    url = f"{config.RMD_BASE_URL}/users/{webaccess_id}/profile"
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=30,
        )
        d = json.loads(resp.read())
        return (d.get("data") or {}).get("attributes", {}).get("name") or ""
    except Exception:
        return ""


def _oa_name(orcid: str) -> str:
    url = f"{config.OPENALEX_BASE_URL}/authors/orcid:{orcid}"
    headers = {"User-Agent": f"mailto:{config.OPENALEX_EMAIL}"}
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=30
        )
        d = json.loads(resp.read())
        return d.get("display_name") or ""
    except Exception:
        return ""


def _ovcount(name: str) -> int:
    if not name:
        return -1
    ident = f"{PSU_ROR} __OVSEP__ {name} __OVSEP__ {name.lower()}"
    d = _ovget("articles.php", r_open_institution_authors=ident)
    return d.get("query", {}).get("total_results", -1)


def _baseline(orcid: str) -> int:
    d = _ovget("articles.php", query=orcid, sort="relevance")
    return d.get("query", {}).get("total_results", -1)


def main() -> None:
    map_path = config.DATA_DIR / config.ORCID_WEBACCESS_MAP
    orcid_map = load_json(map_path, {})
    if not orcid_map:
        print("No ORCID map found")
        return

    random.seed(42)
    sample = random.sample(list(orcid_map.items()), min(SAMPLE_SIZE, len(orcid_map)))
    print(f"Sampling {len(sample)} of {len(orcid_map)} mapped researchers\n")

    rows = []
    for orcid, uid in tqdm(sample, desc="comparing names"):
        rmd = _rmd_name(uid)
        time.sleep(0.3)
        oa = _oa_name(orcid)
        time.sleep(0.1)
        base = _baseline(orcid)
        time.sleep(0.2)
        rmd_ct = _ovcount(rmd)
        time.sleep(0.2)
        oa_ct = _ovcount(oa)
        time.sleep(0.2)
        rows.append({
            "orcid": orcid, "uid": uid,
            "rmd_name": rmd, "oa_name": oa,
            "baseline": base, "rmd_count": rmd_ct, "oa_count": oa_ct,
            "names_differ": rmd != oa,
        })

    # Classify
    both_match = rmd_wins = oa_wins = both_zero = both_match_partial = neither = 0
    baseline_zero = 0
    for r in rows:
        if r["baseline"] == 0:
            baseline_zero += 1
            continue
        if r["rmd_count"] == r["baseline"] and r["oa_count"] == r["baseline"]:
            both_match += 1
        elif r["rmd_count"] == r["baseline"]:
            rmd_wins += 1
        elif r["oa_count"] == r["baseline"]:
            oa_wins += 1
        elif r["rmd_count"] == 0 and r["oa_count"] == 0:
            both_zero += 1
        elif r["rmd_count"] == r["oa_count"]:
            both_match_partial += 1
        else:
            neither += 1

    non_zero_baseline = len(rows) - baseline_zero
    print("\n=== Summary (of researchers with baseline > 0) ===")
    print(f"  total with baseline > 0:         {non_zero_baseline}")
    print(f"  Both recovered full baseline:    {both_match}")
    print(f"  Only RMD-name recovered baseline:{rmd_wins}")
    print(f"  Only OA-name recovered baseline: {oa_wins}")
    print(f"  Both found same but partial:     {both_match_partial}")
    print(f"  Both returned zero:              {both_zero}")
    print(f"  Different partial:               {neither}")
    print(f"  (baseline was 0):                {baseline_zero}")

    # Per-source hit rate (non-zero response)
    rmd_nonzero = sum(1 for r in rows if r["rmd_count"] > 0)
    oa_nonzero = sum(1 for r in rows if r["oa_count"] > 0)
    print(f"\n  RMD name returned >0 articles:   {rmd_nonzero}/{len(rows)}  ({rmd_nonzero/len(rows):.0%})")
    print(f"  OA name returned >0 articles:    {oa_nonzero}/{len(rows)}  ({oa_nonzero/len(rows):.0%})")

    # Average recovery
    rmd_recovery = []
    oa_recovery = []
    for r in rows:
        if r["baseline"] > 0:
            rmd_recovery.append(max(r["rmd_count"], 0) / r["baseline"])
            oa_recovery.append(max(r["oa_count"], 0) / r["baseline"])
    if rmd_recovery:
        print(f"  RMD avg fraction of baseline recovered: {sum(rmd_recovery)/len(rmd_recovery):.2f}")
        print(f"  OA  avg fraction of baseline recovered: {sum(oa_recovery)/len(oa_recovery):.2f}")

    print("\n=== Rows where RMD and OA disagree ===")
    disagreements = [r for r in rows if r["rmd_count"] != r["oa_count"]]
    for r in disagreements[:20]:
        marker = ""
        if r["rmd_count"] == r["baseline"] and r["oa_count"] != r["baseline"]:
            marker = " (RMD wins)"
        elif r["oa_count"] == r["baseline"] and r["rmd_count"] != r["baseline"]:
            marker = " (OA wins)"
        print(f"  base={r['baseline']:<4} rmd={r['rmd_count']:<4} oa={r['oa_count']:<4} "
              f"RMD:{r['rmd_name']!r:<32} OA:{r['oa_name']!r}{marker}")

    out_path = config.DATA_DIR / "rmd_vs_openalex_name_test.json"
    save_json({"rows": rows}, out_path)
    print(f"\nDetail written to {out_path}")


if __name__ == "__main__":
    main()
