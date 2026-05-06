import requests
import logging
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='openalex_collector.log',
                    filemode='a')

class OpenAlexClient:
    def __init__(self, email=None):
        self.base_url = "https://api.openalex.org"
        # Use email from env or default if not provided
        self.email = email or os.getenv('OPENALEX_EMAIL') or "mail@example.com"
        self.headers = {
            "User-Agent": f"mailto:{self.email}"
        }

    def get_psu_dois(self):
        """
        Fetches all DOIs for Penn State research documents from the OpenAlex API.
        """
        dois = []
        cursor = "*"
        page_count = 0
        
        # PSU OpenAlex ID: i130769515
        # Filter for PSU and years 2020-2025 as per example
        filter_param = "authorships.institutions.lineage:i130769515,publication_year:2020-2025"

        print(f"Starting fetch from {self.base_url} with filter: {filter_param}")
        
        while True:
            try:
                params = {
                    "filter": filter_param,
                    "per_page": 200,
                    "cursor": cursor,
                    "select": "doi"
                }
                response = requests.get(f"{self.base_url}/works", headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                
                if not results:
                    break

                for result in results:
                    if result.get("doi"):
                        dois.append(result["doi"])
                
                page_count += 1
                msg = f"Page {page_count}: Fetched {len(results)} results, {len(dois)} total DOIs collected."
                logging.info(msg)
                print(msg) # Print to stdout as well for immediate feedback
                
                # Get next cursor
                cursor = data.get("meta", {}).get("next_cursor")
                if not cursor:
                    break

            except requests.exceptions.RequestException as e:
                logging.error(f"An error occurred: {e}")
                print(f"An error occurred: {e}")
                break
        
        return dois

def main():
    # Instantiate client
    client = OpenAlexClient()
    
    # Fetch DOIs
    dois = client.get_psu_dois()
    
    # Save results
    output_dir = 'keep/openalex_exports'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'psu_dois.json')
    
    print(f"Saving {len(dois)} DOIs to {output_path}...")
    try:
        with open(output_path, 'w') as f:
            json.dump(dois, f, indent=4)
        print("DOIs saved successfully.")
    except Exception as e:
        print(f"Failed to save DOIs: {e}")

if __name__ == "__main__":
    main()
