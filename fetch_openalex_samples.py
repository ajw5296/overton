"""Fetch OpenAlex API samples for the same researcher (Donna Korzick) used in RMD samples."""

import requests
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "api_samples")
os.makedirs(OUT, exist_ok=True)

AUTHOR_ID = "A5025227099"
MAILTO = "test@psu.edu"

endpoints = [
    ("openalex_01_author_search", f"https://api.openalex.org/authors?search=Donna+Korzick&per_page=1&mailto={MAILTO}"),
    ("openalex_02_author_full", f"https://api.openalex.org/{AUTHOR_ID}?mailto={MAILTO}"),
    ("openalex_03_author_works", f"https://api.openalex.org/works?filter=authorships.author.id:{AUTHOR_ID}&per_page=3&sort=cited_by_count:desc&mailto={MAILTO}"),
    ("openalex_04_institution_psu", f"https://api.openalex.org/institutions/I130769515?mailto={MAILTO}"),
    ("openalex_05_funder_nih", f"https://api.openalex.org/funders?search=NIH&per_page=1&mailto={MAILTO}"),
    ("openalex_06_source_journal", f"https://api.openalex.org/sources?search=Endocrinology&per_page=1&mailto={MAILTO}"),
    ("openalex_07_topic", f"https://api.openalex.org/topics?search=cardiovascular+aging&per_page=1&mailto={MAILTO}"),
]

for filename, url in endpoints:
    print(f"Fetching {filename}...", end=" ")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        outpath = os.path.join(OUT, f"{filename}.json")
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"OK ({os.path.getsize(outpath):,} bytes)")
    except Exception as e:
        print(f"ERROR: {e}")

print(f"\nAll files saved to {OUT}")
