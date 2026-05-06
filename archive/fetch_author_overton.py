import requests
import json
import sys
import io

# Force UTF-8 output for Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Configuration
API_KEY = "7cb1b1-daf77f-94ed27"
ARTICLES_URL = "https://app.overton.io/articles.php"
DOCUMENTS_URL = "https://app.overton.io/documents.php"

def fetch_author_info(orcid):
    """
    Fetches information about an author from Overton using their ORCID.
    
    Args:
        orcid (str): The ORCID identifier (e.g., "0000-0002-9809-8127")
    """
    print(f"--- Fetching Overton data for ORCID: {orcid} ---\n")
    
    # 1. Search for Articles (Scholarly works by this author in Overton)
    # We use the 'query' parameter with the ORCID directly.
    print(f"Querying Articles Endpoint...")
    params = {
        "api_key": API_KEY,
        "format": "json",
        "query": orcid,
        "sort": "relevance"
    }
    
    try:
        response = requests.get(ARTICLES_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            total = data.get('query', {}).get('total_results', 0)
            print(f"Found {total} scholarly articles matching this ORCID.")
            
            if total > 0:
                print("Sample Article Titles:")
                results = data.get('results', [])
                
                # Handle list (standard) or dict (sometimes returned by Overton)
                if isinstance(results, dict):
                    # If it's a dict, the values are likely the items
                    # print(f"Results is a dict with keys: {list(results.keys())[:3]}")
                    results = list(results.values())

                if isinstance(results, list):
                    if len(results) > 0:
                        first_item = results[0]
                        # print(f"Debug: Type of first item is {type(first_item)}")
                        # print(f"Debug: First item: {str(first_item)[:100]}...")
                        
                        if isinstance(first_item, dict):
                            for result in results[:3]:
                                print(f" - {result.get('title')} ({result.get('published_on')})")
                        elif isinstance(first_item, list):
                             print("Results appear to be a list of lists (raw rows).")
                             print("First row sample:", first_item)
                        else:
                             print(f"Unexpected item type: {type(first_item)}")
                else:
                    print(f"Unexpected results format: {type(results)}")
        else:
            print(f"Error querying articles: {response.status_code}")
            
    except Exception as e:
        print(f"Exception querying articles: {e}")

    print("-" * 30)

    # 2. Search for Documents (Policy documents citing/mentioning this author/ORCID)
    print(f"Querying Policy Documents Endpoint...")
    
    try:
        response = requests.get(DOCUMENTS_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            total = data.get('query', {}).get('total_results', 0)
            print(f"Found {total} policy documents matching this ORCID.")
            
            if total > 0:
                print("Sample Policy Documents:")
                for result in data.get('results', [])[:3]:
                    title = result.get('title')
                    source = result.get('source', {}).get('title')
                    print(f" - {title}")
                    print(f"   Source: {source}")
                    print(f"   URL: {result.get('overton_url')}\n")
        else:
            print(f"Error querying documents: {response.status_code}")
            
    except Exception as e:
        print(f"Exception querying documents: {e}")

if __name__ == "__main__":
    # Default to the test ORCID we found earlier if none provided
    test_orcid = "0000-0002-9809-8127"
    
    if len(sys.argv) > 1:
        test_orcid = sys.argv[1]
        
    fetch_author_info(test_orcid)