import requests
import json

# Fetch the same work as before to get an author's ORCID
doi = "https://doi.org/10.1038/s41586-021-03451-0"
url = f"https://api.openalex.org/works/{doi}"
headers = {"User-Agent": "mailto:example@psu.edu"}

try:
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        authorships = data.get('authorships', [])
        
        print(f"Checking {len(authorships)} authors for ORCID...")
        found_orcid = None
        
        for authorship in authorships:
            author = authorship.get('author', {})
            orcid = author.get('orcid')
            if orcid:
                display_name = author.get('display_name')
                print(f"Found Author: {display_name}, ORCID: {orcid}")
                found_orcid = orcid
                break
        
        if found_orcid:
            # Save it to a file or just print it so I can use it in the next step
            print(f"TEST_ORCID={found_orcid}")
        else:
            print("No ORCID found in this work.")
            
    else:
        print(f"Error: {response.status_code}")
except Exception as e:
    print(f"Error: {e}")