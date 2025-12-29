import requests
import logging
import json
import os
import time
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='psu_researchers_collector.log',
                    filemode='a')


class PSUResearcherFetcher:
    """
    Fetches Penn State affiliated researchers from OpenAlex API.
    Collects ORCID, PSU affiliation, field of research, and DOIs.
    """

    # Penn State University ROR ID
    PSU_ROR = "https://ror.org/04p491231"
    PSU_INSTITUTION_ID = "i130769515"

    def __init__(self, email=None):
        self.base_url = "https://api.openalex.org"
        self.email = email or os.getenv('OPENALEX_EMAIL') or "mail@example.com"
        self.headers = {
            "User-Agent": f"mailto:{self.email}"
        }

    def fetch_researchers(self, max_results=None, test_mode=False, fetch_dois=True):
        """
        Fetches Penn State researchers with ORCIDs.

        Args:
            max_results: Limit the number of results (None for all)
            test_mode: If True, only fetch first page for testing
            fetch_dois: If True, fetch DOIs for each researcher (slower)

        Returns:
            List of researcher dicts with orcid, name, psu_affiliation, field, and dois
        """
        researchers = []
        cursor = "*"
        page_count = 0

        # Filter for authors CURRENTLY affiliated with PSU
        filter_param = f"last_known_institutions.ror:{self.PSU_ROR},has_orcid:true"

        # Select only the fields we need
        select_fields = "id,orcid,display_name,last_known_institutions,affiliations,topics"

        # First, get the total count
        params = {
            "filter": filter_param,
            "per_page": 1
        }
        response = requests.get(f"{self.base_url}/authors", headers=self.headers, params=params)
        response.raise_for_status()
        total_count = response.json().get("meta", {}).get("count", 0)

        print(f"Found {total_count:,} Penn State researchers with ORCIDs")
        logging.info(f"Starting fetch of {total_count} Penn State researchers")

        if test_mode:
            print("TEST MODE: Fetching only first page (up to 200 results)")
            total_to_fetch = min(200, total_count)
        elif max_results:
            total_to_fetch = min(max_results, total_count)
            print(f"Limiting to {total_to_fetch:,} results")
        else:
            total_to_fetch = total_count

        # Progress bar for fetching authors
        pbar = tqdm(total=total_to_fetch, desc="Fetching researchers")

        while True:
            try:
                params = {
                    "filter": filter_param,
                    "per_page": 200,
                    "cursor": cursor,
                    "select": select_fields
                }

                response = requests.get(f"{self.base_url}/authors", headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])

                if not results:
                    break

                for author in results:
                    researcher = self._parse_author(author)
                    if researcher:
                        researchers.append(researcher)
                        pbar.update(1)

                        if max_results and len(researchers) >= max_results:
                            break

                page_count += 1
                logging.info(f"Page {page_count}: Fetched {len(results)} authors, {len(researchers)} total")

                # Check if we've reached our limit
                if max_results and len(researchers) >= max_results:
                    break

                if test_mode:
                    break

                # Get next cursor
                cursor = data.get("meta", {}).get("next_cursor")
                if not cursor:
                    break

                time.sleep(0.1)

            except requests.exceptions.RequestException as e:
                logging.error(f"Request error: {e}")
                print(f"\nRequest error: {e}")
                break

        pbar.close()

        # Fetch DOIs for each researcher
        if fetch_dois and researchers:
            print(f"\nFetching DOIs for {len(researchers)} researchers...")
            self._fetch_dois_for_researchers(researchers)

        return researchers

    def _parse_author(self, author):
        """
        Extracts relevant fields from an author record.
        """
        orcid = author.get("orcid")
        if not orcid:
            return None

        # Check if PSU is in their current affiliations
        last_institutions = author.get("last_known_institutions", [])
        is_currently_at_psu = any(
            inst.get("ror") == self.PSU_ROR for inst in last_institutions
        )

        if not is_currently_at_psu:
            return None

        # Get PSU affiliation with years from affiliations history
        affiliations_raw = author.get("affiliations", [])
        psu_affiliation = None
        for aff in affiliations_raw:
            inst = aff.get("institution", {})
            if inst.get("ror") == self.PSU_ROR:
                years = aff.get("years", [])
                psu_affiliation = {
                    "name": inst.get("display_name"),
                    "years": sorted(years) if years else []
                }
                break

        # Get primary field of research (first topic)
        topics = author.get("topics", [])
        field_of_research = None
        if topics:
            topic = topics[0]
            field_of_research = {
                "topic": topic.get("display_name"),
                "subfield": topic.get("subfield", {}).get("display_name") if topic.get("subfield") else None,
                "field": topic.get("field", {}).get("display_name") if topic.get("field") else None,
                "domain": topic.get("domain", {}).get("display_name") if topic.get("domain") else None
            }

        # Extract author ID for DOI lookup
        author_id = author.get("id", "").replace("https://openalex.org/", "")

        return {
            "orcid": orcid,
            "display_name": author.get("display_name"),
            "openalex_id": author_id,
            "psu_affiliation": psu_affiliation,
            "field_of_research": field_of_research,
            "psu_dois": []  # Will be populated by _fetch_dois_for_researchers
        }

    def _fetch_dois_for_researchers(self, researchers):
        """
        Fetches DOIs for works authored while at Penn State for each researcher.
        """
        pbar = tqdm(researchers, desc="Fetching DOIs")

        for researcher in pbar:
            author_id = researcher.get("openalex_id")
            if not author_id:
                continue

            psu_years = researcher.get("psu_affiliation", {}).get("years", [])
            if not psu_years:
                continue

            min_year = min(psu_years)
            max_year = max(psu_years)

            # Fetch works by this author at PSU during their affiliation years
            dois = self._fetch_author_psu_dois(author_id, min_year, max_year)
            researcher["psu_dois"] = dois

            time.sleep(0.05)  # Small delay between requests

    def _fetch_author_psu_dois(self, author_id, min_year, max_year):
        """
        Fetches DOIs for an author's works at Penn State within given years.
        """
        dois = []
        cursor = "*"

        # Filter for works by this author, at PSU, within their PSU years
        filter_param = (
            f"author.id:{author_id},"
            f"authorships.institutions.ror:{self.PSU_ROR},"
            f"publication_year:{min_year}-{max_year}"
        )

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

                for work in results:
                    doi = work.get("doi")
                    if doi:
                        dois.append(doi)

                cursor = data.get("meta", {}).get("next_cursor")
                if not cursor:
                    break

            except requests.exceptions.RequestException as e:
                logging.error(f"Error fetching DOIs for {author_id}: {e}")
                break

        return dois


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Penn State researchers from OpenAlex")
    parser.add_argument("--test", action="store_true", help="Test mode: fetch only first page")
    parser.add_argument("--max", type=int, default=None, help="Maximum number of results to fetch")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--no-dois", action="store_true", help="Skip fetching DOIs (faster)")
    args = parser.parse_args()

    # Create fetcher
    fetcher = PSUResearcherFetcher()

    # Fetch researchers
    researchers = fetcher.fetch_researchers(
        max_results=args.max,
        test_mode=args.test,
        fetch_dois=not args.no_dois
    )

    # Determine output path
    output_dir = 'keep/openalex_exports'
    os.makedirs(output_dir, exist_ok=True)

    if args.output:
        output_path = args.output
    elif args.test:
        output_path = os.path.join(output_dir, 'psu_researchers_test.json')
    else:
        output_path = os.path.join(output_dir, 'psu_researchers.json')

    # Save results
    print(f"\nSaving {len(researchers)} researchers to {output_path}...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(researchers, f, indent=2, ensure_ascii=False)
        print("Saved successfully.")
    except Exception as e:
        print(f"Failed to save: {e}")
        logging.error(f"Failed to save results: {e}")

    # Print sample
    if researchers:
        print("\n--- Sample Results ---")
        for r in researchers[:3]:
            print(f"\nName: {r['display_name']}")
            print(f"ORCID: {r['orcid']}")
            if r['psu_affiliation']:
                years = r['psu_affiliation'].get('years', [])
                if years:
                    print(f"PSU Years: {min(years)}-{max(years)}")
            if r['field_of_research']:
                print(f"Field: {r['field_of_research']['field']} > {r['field_of_research']['subfield']}")
            print(f"PSU DOIs: {len(r.get('psu_dois', []))}")


if __name__ == "__main__":
    main()
