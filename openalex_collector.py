import os
import json
from openalex_client import OpenAlexClient
from dotenv import load_dotenv

load_dotenv()

def collect_dois():
    """
    Initializes the OpenAlex client, fetches PSU DOIs, and saves them to a file.
    """
    email = os.getenv("OPENALEX_EMAIL")
    if not email:
        raise ValueError("OPENALEX_EMAIL environment variable not set.")

    client = OpenAlexClient(email)
    dois = client.get_psu_dois()

    output_dir = "data/openalex_exports"
    os.makedirs(output_dir, exist_ok=True)
    
    with open(f"{output_dir}/psu_dois.json", "w") as f:
        json.dump(dois, f, indent=4)
    
    print(f"Successfully collected {len(dois)} DOIs and saved them to {output_dir}/psu_dois.json")

if __name__ == "__main__":
    collect_dois()