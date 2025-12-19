import requests
import json

api_key = "7cb1b1-daf77f-94ed27"
orcid = "0000-0002-9809-8127" # Stripped of URL prefix just in case
full_orcid = "https://orcid.org/0000-0002-9809-8127"

endpoints = [
    ("https://app.overton.io/articles.php", "articles"),
    ("https://app.overton.io/documents.php", "documents")
]

variations = [
    {"orcid": orcid},
    {"orcid": full_orcid},
    {"author_orcid": orcid},
    {"query": f'orcid:"{orcid}"'},
    {"query": orcid}
]

print(f"Testing ORCID lookup for: {orcid}")

for url, name in endpoints:
    print(f"\n--- Testing endpoint: {name} ({url}) ---")
    for params in variations:
        current_params = {
            "api_key": api_key,
            "format": "json",
            **params
        }
        print(f"  Params: {params}")
        try:
            response = requests.get(url, params=current_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                total = data.get('query', {}).get('total_results', 0)
                print(f"    Status: 200, Total Results: {total}")
                if total > 0:
                    print(f"    SUCCESS! Found {total} results.")
                    # print(json.dumps(data.get('results', [])[:1], indent=2))
            else:
                print(f"    Status: {response.status_code}")
        except Exception as e:
            print(f"    Error: {e}")
