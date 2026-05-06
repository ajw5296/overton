"""Fetch raw JSON from every RMD API endpoint and save to api_samples/."""

import requests
import json
import os

BASE_URL = "https://metadata.libraries.psu.edu/v1"
API_KEY = "264d2e02f4c8089b594de2ad8db5f80c0ada5828deca6f06a4d5690d4cd80f869e44aa32b7e4dead64a56f963b368be7"
HEADERS = {"X-API-Key": API_KEY, "Accept": "application/json"}
OUT_DIR = os.path.join(os.path.dirname(__file__), "api_samples")
os.makedirs(OUT_DIR, exist_ok=True)

EXAMPLE_USER = "dhk102"
EXAMPLE_ORG_ID = "187"  # Human Development and Family Studies
EXAMPLE_PUB_ID = "4"

endpoints = [
    ("01_GET_organizations",               "GET",  "/organizations",                                    None, None),
    ("02_GET_org_publications",            "GET",  f"/organizations/{EXAMPLE_ORG_ID}/publications",     {"limit": 3, "offset": 0}, None),
    ("03_GET_all_publications",            "GET",  "/publications",                                     {"limit": 3}, None),
    ("04_GET_single_publication",          "GET",  f"/publications/{EXAMPLE_PUB_ID}",                   None, None),
    ("05_GET_publication_grants",          "GET",  f"/publications/{EXAMPLE_PUB_ID}/grants",            None, None),
    ("06_GET_user_profile",                "GET",  f"/users/{EXAMPLE_USER}/profile",                    None, None),
    ("07_GET_user_publications",           "GET",  f"/users/{EXAMPLE_USER}/publications",               {"limit": 3, "order_first_by": "citation_count_desc"}, None),
    ("08_GET_user_org_memberships",        "GET",  f"/users/{EXAMPLE_USER}/organization_memberships",   None, None),
    ("09_GET_user_grants",                 "GET",  f"/users/{EXAMPLE_USER}/grants",                     None, None),
    ("10_GET_user_presentations",          "GET",  f"/users/{EXAMPLE_USER}/presentations",              None, None),
    ("11_GET_user_news_feed_items",        "GET",  f"/users/{EXAMPLE_USER}/news_feed_items",            None, None),
    ("12_GET_user_performances",           "GET",  f"/users/{EXAMPLE_USER}/performances",               None, None),
    ("13_GET_user_etds",                   "GET",  f"/users/{EXAMPLE_USER}/etds",                       None, None),
    ("14_POST_bulk_users_publications",    "POST", "/users/publications",                               {"limit": 2, "order_first_by": "citation_count_desc"}, [EXAMPLE_USER, "acr6"]),
]

for filename, method, path, params, body in endpoints:
    url = f"{BASE_URL}{path}"
    print(f"Fetching {method} {path}...", end=" ")
    try:
        if method == "GET":
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        else:
            resp = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"},
                                 params=params, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        outpath = os.path.join(OUT_DIR, f"{filename}.json")
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"OK ({os.path.getsize(outpath):,} bytes)")
    except Exception as e:
        print(f"ERROR: {e}")

print(f"\nAll files saved to {OUT_DIR}")
