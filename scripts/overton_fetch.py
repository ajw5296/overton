import json
import requests
import time
import os
from tqdm import tqdm

# Configuration
API_KEY = "7cb1b1-daf77f-94ed27"
INPUT_FILE = "keep/openalex_exports/psu_dois.json"
OUTPUT_FILE = "keep/overton_hits.json"
SAMPLE_SIZE = 100
DOCUMENTS_URL = "https://app.overton.io/documents.php"

def fetch_overton_data():
    # Read DOIs
    print(f"Reading DOIs from {INPUT_FILE}...")
    try:
        with open(INPUT_FILE, 'r') as f:
            dois = json.load(f)
    except FileNotFoundError:
        print(f"Error: File {INPUT_FILE} not found.")
        return

    # Take sample
    sample_dois = dois[:SAMPLE_SIZE]
    print(f"Processing {len(sample_dois)} DOIs...")

    hits = []
    
    # Progress bar
    for doi in tqdm(sample_dois):
        # The DOI string in the file is like "https://doi.org/10.1080/..."
        # We'll try querying with the full string first as suggested
        
        # We can also try stripping the prefix if we want to be thorough, 
        # but let's start with the exact string from the file.
        query_val = f'"{doi}"' # Quote it to be specific? Or raw? 
        # User example: "query": "10.1186/..." (no quotes inside the value)
        # But if it contains slashes/colons, quotes might help for exact phrase.
        # Let's try raw first, similar to the user's example.
        
        params = {
            "api_key": API_KEY,
            "format": "json",
            "query": doi,  # Use the full DOI string
            "sort": "relevance"
        }

        try:
            response = requests.get(DOCUMENTS_URL, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                total_results = data.get('query', {}).get('total_results', 0)
                
                if total_results > 0:
                    print(f"\n[HIT] Found {total_results} documents for DOI: {doi}")
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

        # Rate limiting (conservative)
        time.sleep(0.5)

    # Save results
    print(f"\nFinished. Found hits for {len(hits)} DOIs.")
    if hits:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(hits, f, indent=2)
        print(f"Results saved to {OUTPUT_FILE}")
    else:
        print("No hits found in this sample.")

if __name__ == "__main__":
    fetch_overton_data()