import requests
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='openalex_collector.log',
                    filemode='a')

class OpenAlexClient:
    def __init__(self, email):
        self.base_url = "https://api.openalex.org"
        self.headers = {
            "User-Agent": f"mailto:{email}"
        }

    def get_psu_dois(self):
        """
        Fetches all DOIs for Penn State research documents from the OpenAlex API.
        """
        dois = []
        cursor = "*"
        page_count = 0
        
        while True:
            try:
                params = {
                    "filter": "authorships.institutions.lineage:i130769515,publication_year:2020-2025",
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
                logging.info(f"Page {page_count}: Fetched {len(results)} results, {len(dois)} total DOIs collected.")
                
                # Get next cursor
                cursor = data.get("meta", {}).get("next_cursor")
                if not cursor:
                    break

            except requests.exceptions.RequestException as e:
                logging.error(f"An error occurred: {e}")
                break
        
        return dois