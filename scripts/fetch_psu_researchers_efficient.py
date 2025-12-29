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


class PSUDataFetcher:
    """
    Fetches Penn State researchers and works from OpenAlex API.
    Saves as separate datasets for later matching/analysis.
    """

    PSU_ROR = "https://ror.org/04p491231"

    def __init__(self, email=None):
        self.base_url = "https://api.openalex.org"
        self.email = email or os.getenv('OPENALEX_EMAIL') or "mail@example.com"
        self.headers = {
            "User-Agent": f"mailto:{self.email}"
        }

    def fetch_researchers(self, max_results=None, current_only=False):
        """
        Fetch PSU-affiliated researchers (current and past).

        Args:
            max_results: Limit results (None for all)
            current_only: If True, only fetch currently affiliated researchers
        """
        researchers = []
        cursor = "*"

        # Filter: all researchers ever affiliated with PSU, with ORCIDs
        if current_only:
            filter_param = f"last_known_institutions.ror:{self.PSU_ROR},has_orcid:true"
        else:
            filter_param = f"affiliations.institution.ror:{self.PSU_ROR},has_orcid:true"

        select_fields = "id,orcid,display_name,affiliations,topics"

        # Get total count
        response = requests.get(
            f"{self.base_url}/authors",
            headers=self.headers,
            params={"filter": filter_param, "per_page": 1}
        )
        response.raise_for_status()
        total_count = response.json().get("meta", {}).get("count", 0)

        to_fetch = min(max_results, total_count) if max_results else total_count
        print(f"Found {total_count:,} researchers, fetching {to_fetch:,}")

        pbar = tqdm(total=to_fetch, desc="Researchers")

        while len(researchers) < to_fetch:
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
                parsed = self._parse_author(author)
                if parsed:
                    researchers.append(parsed)
                    pbar.update(1)
                    if max_results and len(researchers) >= max_results:
                        break

            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break

            time.sleep(0.1)

        pbar.close()
        return researchers

    def fetch_works(self, max_results=None):
        """
        Fetch all PSU-affiliated works with author IDs.

        Args:
            max_results: Limit results (None for all)
        """
        works = []
        cursor = "*"

        filter_param = f"authorships.institutions.ror:{self.PSU_ROR}"
        select_fields = "doi,authorships,publication_year,title"

        # Get total count
        response = requests.get(
            f"{self.base_url}/works",
            headers=self.headers,
            params={"filter": filter_param, "per_page": 1}
        )
        response.raise_for_status()
        total_count = response.json().get("meta", {}).get("count", 0)

        to_fetch = min(max_results, total_count) if max_results else total_count
        print(f"Found {total_count:,} works, fetching {to_fetch:,}")

        pbar = tqdm(total=to_fetch, desc="Works")

        while len(works) < to_fetch:
            params = {
                "filter": filter_param,
                "per_page": 200,
                "cursor": cursor,
                "select": select_fields
            }

            response = requests.get(f"{self.base_url}/works", headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if not results:
                break

            for work in results:
                parsed = self._parse_work(work)
                if parsed:
                    works.append(parsed)
                    pbar.update(1)
                    if max_results and len(works) >= max_results:
                        break

            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break

            time.sleep(0.1)

        pbar.close()
        return works

    def _parse_author(self, author):
        """Parse author data from API response."""
        orcid = author.get("orcid")
        if not orcid:
            return None

        author_id = author.get("id", "").replace("https://openalex.org/", "")

        # Get PSU affiliation with years
        psu_affiliation = None
        for aff in author.get("affiliations", []):
            inst = aff.get("institution", {})
            if inst.get("ror") == self.PSU_ROR:
                years = aff.get("years", [])
                psu_affiliation = {
                    "name": inst.get("display_name"),
                    "years": sorted(years) if years else []
                }
                break

        # Get field of research
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

        return {
            "orcid": orcid,
            "display_name": author.get("display_name"),
            "openalex_id": author_id,
            "psu_affiliation": psu_affiliation,
            "field_of_research": field_of_research
        }

    def _parse_work(self, work):
        """Parse work data from API response."""
        doi = work.get("doi")
        if not doi:
            return None

        # Extract all authors in order of authorship
        authors = []
        has_psu_author = False

        for authorship in work.get("authorships", []):
            author_data = authorship.get("author") or {}
            author_id_raw = author_data.get("id") or ""
            author_id = author_id_raw.replace("https://openalex.org/", "")
            institutions = authorship.get("institutions", [])

            # Check if this author was at PSU for this work
            is_psu = any(inst.get("ror") == self.PSU_ROR for inst in institutions)
            if is_psu:
                has_psu_author = True

            # Get ORCID (clean up the URL format if present)
            orcid_raw = author_data.get("orcid")
            orcid = orcid_raw.replace("https://orcid.org/", "") if orcid_raw else None

            authors.append({
                "openalex_id": author_id,
                "display_name": author_data.get("display_name"),
                "orcid": orcid,
                "position": authorship.get("author_position"),
                "is_psu": is_psu
            })

        # Only include works that have at least one PSU author
        if not has_psu_author:
            return None

        return {
            "doi": doi,
            "title": work.get("title"),
            "publication_year": work.get("publication_year"),
            "authors": authors
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Penn State researchers and works from OpenAlex")
    parser.add_argument("--researchers", action="store_true", help="Fetch researchers")
    parser.add_argument("--works", action="store_true", help="Fetch works")
    parser.add_argument("--all", action="store_true", help="Fetch both researchers and works")
    parser.add_argument("--current-only", action="store_true", help="Only fetch currently affiliated researchers")
    parser.add_argument("--max-researchers", type=int, default=None, help="Max researchers to fetch")
    parser.add_argument("--max-works", type=int, default=None, help="Max works to fetch")
    parser.add_argument("--test", action="store_true", help="Test mode: limited data")
    args = parser.parse_args()

    # Default to --all if nothing specified
    if not args.researchers and not args.works and not args.all:
        args.all = True

    if args.test:
        args.max_researchers = args.max_researchers or 200
        args.max_works = args.max_works or 1000

    fetcher = PSUDataFetcher()
    output_dir = 'keep/openalex_exports'
    os.makedirs(output_dir, exist_ok=True)

    # Fetch researchers
    if args.researchers or args.all:
        print("\n" + "=" * 50)
        print("Fetching PSU Researchers...")
        print("=" * 50)

        researchers = fetcher.fetch_researchers(
            max_results=args.max_researchers,
            current_only=args.current_only
        )

        suffix = "_current" if args.current_only else ""
        suffix += "_test" if args.test else ""
        output_path = os.path.join(output_dir, f'psu_researchers{suffix}.json')

        print(f"\nSaving {len(researchers):,} researchers to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(researchers, f, indent=2, ensure_ascii=False)
        print("Saved.")

    # Fetch works
    if args.works or args.all:
        print("\n" + "=" * 50)
        print("Fetching PSU Works...")
        print("=" * 50)

        works = fetcher.fetch_works(max_results=args.max_works)

        suffix = "_test" if args.test else ""
        output_path = os.path.join(output_dir, f'psu_works{suffix}.json')

        print(f"\nSaving {len(works):,} works to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(works, f, indent=2, ensure_ascii=False)
        print("Saved.")

    print("\nDone!")


if __name__ == "__main__":
    main()
