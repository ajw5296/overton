import json
import requests
import time
import os
import argparse
from tqdm import tqdm

# Configuration
API_KEY = "7cb1b1-daf77f-94ed27"
ARTICLES_URL = "https://app.overton.io/articles.php"
DOCUMENTS_URL = "https://app.overton.io/documents.php"


def fetch_by_orcids(input_file, output_file, sample_size=None):
    """
    Fetch Overton data for researchers by ORCID.
    Queries both articles and documents endpoints.
    """
    print(f"Reading researchers from {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        researchers = json.load(f)

    # Apply sample size if specified
    if sample_size:
        researchers = researchers[:sample_size]

    print(f"Processing {len(researchers)} researchers...")

    results = []

    for researcher in tqdm(researchers):
        orcid_raw = researcher.get("orcid", "")
        # Strip URL prefix if present
        orcid = orcid_raw.replace("https://orcid.org/", "")

        if not orcid:
            continue

        researcher_result = {
            "orcid": orcid,
            "display_name": researcher.get("display_name"),
            "openalex_id": researcher.get("openalex_id"),
            "field_of_research": researcher.get("field_of_research"),
            "articles": None,
            "policy_documents": None
        }

        params = {
            "api_key": API_KEY,
            "format": "json",
            "query": orcid,
            "sort": "relevance"
        }

        # Query Articles endpoint
        try:
            response = requests.get(ARTICLES_URL, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                total = data.get('query', {}).get('total_results', 0)
                if total > 0:
                    researcher_result["articles"] = {
                        "total": total,
                        "results": data.get('results', [])
                    }
            elif response.status_code == 429:
                print("\nRate limited on articles. Waiting...")
                time.sleep(5)
        except Exception as e:
            print(f"\nArticles request failed for {orcid}: {e}")

        time.sleep(0.3)  # Rate limiting between requests

        # Query Documents (policy) endpoint
        try:
            response = requests.get(DOCUMENTS_URL, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                total = data.get('query', {}).get('total_results', 0)
                if total > 0:
                    researcher_result["policy_documents"] = {
                        "total": total,
                        "results": data.get('results', [])
                    }
            elif response.status_code == 429:
                print("\nRate limited on documents. Waiting...")
                time.sleep(5)
        except Exception as e:
            print(f"\nDocuments request failed for {orcid}: {e}")

        # Only include researchers with at least one hit
        if researcher_result["articles"] or researcher_result["policy_documents"]:
            results.append(researcher_result)

        time.sleep(0.3)  # Rate limiting between researchers

    # Summary
    articles_count = sum(1 for r in results if r["articles"])
    docs_count = sum(1 for r in results if r["policy_documents"])

    print(f"\nFinished. Found {len(results)} researchers with Overton data:")
    print(f"  - {articles_count} with articles")
    print(f"  - {docs_count} with policy documents")

    # Save results to separate files
    if results:
        output_dir = os.path.dirname(output_file)
        os.makedirs(output_dir, exist_ok=True)

        # Combined results
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Combined results saved to {output_file}")

        # Articles only
        articles_results = []
        for r in results:
            if r["articles"]:
                articles_results.append({
                    "orcid": r["orcid"],
                    "display_name": r["display_name"],
                    "openalex_id": r["openalex_id"],
                    "field_of_research": r["field_of_research"],
                    "articles": r["articles"]
                })

        if articles_results:
            articles_file = output_file.replace(".json", "_articles.json")
            with open(articles_file, 'w', encoding='utf-8') as f:
                json.dump(articles_results, f, indent=2, ensure_ascii=False)
            print(f"Articles saved to {articles_file}")

        # Policy documents only
        docs_results = []
        for r in results:
            if r["policy_documents"]:
                docs_results.append({
                    "orcid": r["orcid"],
                    "display_name": r["display_name"],
                    "openalex_id": r["openalex_id"],
                    "field_of_research": r["field_of_research"],
                    "policy_documents": r["policy_documents"]
                })

        if docs_results:
            docs_file = output_file.replace(".json", "_policy_documents.json")
            with open(docs_file, 'w', encoding='utf-8') as f:
                json.dump(docs_results, f, indent=2, ensure_ascii=False)
            print(f"Policy documents saved to {docs_file}")
    else:
        print("No hits found.")


def fetch_by_dois(input_file, output_file, sample_size=None):
    """
    Fetch Overton data by DOIs (documents endpoint only).
    """
    print(f"Reading DOIs from {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        dois = json.load(f)

    if sample_size:
        dois = dois[:sample_size]

    print(f"Processing {len(dois)} DOIs...")

    hits = []

    for doi in tqdm(dois):
        params = {
            "api_key": API_KEY,
            "format": "json",
            "query": doi,
            "sort": "relevance"
        }

        try:
            response = requests.get(DOCUMENTS_URL, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                total_results = data.get('query', {}).get('total_results', 0)

                if total_results > 0:
                    hits.append({
                        "doi": doi,
                        "total_results": total_results,
                        "results": data.get('results', [])
                    })
            elif response.status_code == 429:
                print("\nRate limited. Waiting...")
                time.sleep(5)
            else:
                print(f"\nError {response.status_code} for {doi}")

        except Exception as e:
            print(f"\nRequest failed for {doi}: {e}")

        time.sleep(0.5)

    print(f"\nFinished. Found hits for {len(hits)} DOIs.")
    if hits:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(hits, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {output_file}")
    else:
        print("No hits found.")


def main():
    parser = argparse.ArgumentParser(description="Fetch data from Overton API")
    parser.add_argument("--mode", choices=["orcid", "doi"], default="orcid",
                        help="Query mode: 'orcid' for researchers, 'doi' for works")
    parser.add_argument("--input", type=str, default="keep/openalex_exports/psu_social_science_2025.json",
                        help="Input JSON file")
    parser.add_argument("--output", type=str, default="keep/overton_exports/social_science_overton.json",
                        help="Output JSON file")
    parser.add_argument("--sample", type=int, default=None,
                        help="Limit to first N items (for testing)")
    args = parser.parse_args()

    if args.mode == "orcid":
        fetch_by_orcids(args.input, args.output, args.sample)
    else:
        fetch_by_dois(args.input, args.output, args.sample)


if __name__ == "__main__":
    main()
