import requests
import json

# OpenAlex API endpoint for a single work
# Using one of the DOIs from our previous Overton hits as an example
doi = "https://doi.org/10.1038/s41586-021-03451-0"
base_url = "https://api.openalex.org/works/"

# It's good practice to include your email in the User-Agent header 
# so OpenAlex can contact you if there are issues.
headers = {
    "User-Agent": "mailto:example@psu.edu"
}

print(f"Fetching metadata for DOI: {doi}")
url = f"{base_url}{doi}"

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        # Print some basic details
        print("\n--- Work Details ---")
        print(f"Title: {data.get('title')}")
        print(f"Publication Year: {data.get('publication_year')}")
        print(f"Cited by Count: {data.get('cited_by_count')}")
        
        # Print first author
        authorships = data.get('authorships', [])
        if authorships:
            first_author = authorships[0].get('author', {}).get('display_name')
            print(f"First Author: {first_author}")
            
        print(f"OpenAlex ID: {data.get('id')}")
        
        # Show a snippet of the raw JSON
        print("\n--- Raw JSON Snippet (first 500 chars) ---")
        print(json.dumps(data, indent=2)[:500] + "...")
        
    else:
        print(f"Error: {response.text}")

except Exception as e:
    print(f"An error occurred: {e}")