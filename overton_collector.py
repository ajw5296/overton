import os
import json
import pandas as pd
from api_client import OvertonAPIClient
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

def collect_overton_data(limit=None):
    """
    Initializes the Overton client, loads DOIs, queries the Overton API, and saves the results.
    """
    api_key = os.getenv("OVERTON_API_KEY")
    if not api_key:
        raise ValueError("OVERTON_API_KEY environment variable not set.")

    client = OvertonAPIClient(api_key)
    
    # Load DOIs
    doi_file = "data/openalex_exports/psu_dois.json"
    with open(doi_file, "r") as f:
        dois = json.load(f)

    if limit:
        dois = dois[:limit]

    results = []
    with tqdm(total=len(dois), desc="Querying Overton by DOI") as pbar:
        for doi in dois:
            cleaned_doi = doi.replace("https://doi.org/", "")
            result = client.query_by_doi(cleaned_doi)
            results.append(result)
            pbar.update(1)

    # Process and save results
    output_dir = "results"
    os.makedirs(output_dir, exist_ok=True)
    
    df = pd.DataFrame(results)
    df.to_csv(f"{output_dir}/overton_doi_results.csv", index=False)
    
    print(f"Successfully queried {len(dois)} DOIs and saved the results to {output_dir}/overton_doi_results.csv")

if __name__ == "__main__":
    # pass limit=10 to run on a subset of DOIs
    collect_overton_data(limit=10)