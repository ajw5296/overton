import requests
import json
import os

# The URL provided by the user
url = "https://api.openalex.org/authors?page=1&filter=has_orcid:true,last_known_institutions.id:i130769515&sort=works_count:desc&per_page=10&mailto=ui@openalex.org"

print(f"Fetching data from: {url}")

try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        # Save to JSON file
        output_filename = "openalex_query_result.json"
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        print(f"Successfully saved output to {output_filename}")
        
        # Show a snippet of the output as requested
        print("\n--- Output Snippet ---")
        meta = data.get('meta', {})
        print(f"Meta count: {meta.get('count')}")
        
        results = data.get('results', [])
        print(f"Number of results fetched: {len(results)}")
        
        if results:
            first_author = results[0]
            print("\nFirst Author in results:")
            print(f"Name: {first_author.get('display_name')}")
            print(f"ORCID: {first_author.get('orcid')}")
            print(f"Works Count: {first_author.get('works_count')}")
            print(f"Institution: {first_author.get('last_known_institution', {}).get('display_name')}")
            
    else:
        print(f"Error: {response.text}")

except Exception as e:
    print(f"An error occurred: {e}")