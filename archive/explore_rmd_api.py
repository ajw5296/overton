"""
Explore Penn State's Researcher Metadata Database (RMD) API.

API Docs: https://metadata.libraries.psu.edu/api_docs
Spec: https://metadata.libraries.psu.edu/api-docs/v1/swagger.yaml
"""

import requests
import json
import os
import sys
import io

# Force UTF-8 output for Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_URL = "https://metadata.libraries.psu.edu/v1"
API_KEY = os.environ.get("RMD_API_KEY", "264d2e02f4c8089b594de2ad8db5f80c0ada5828deca6f06a4d5690d4cd80f869e44aa32b7e4dead64a56f963b368be7")

HEADERS = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
}


def api_get(path, params=None):
    """Make a GET request to the RMD API."""
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(path, body, params=None):
    """Make a POST request to the RMD API."""
    url = f"{BASE_URL}{path}"
    resp = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"},
                         json=body, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def explore_organizations():
    """List all organizations available via the API."""
    print("=" * 70)
    print("ORGANIZATIONS")
    print("=" * 70)
    data = api_get("/organizations")
    orgs = data.get("data", [])
    print(f"Total organizations: {len(orgs)}\n")
    for org in orgs:
        attrs = org.get("attributes", {})
        print(f"  ID: {org['id']:>5}  |  {attrs.get('name', 'N/A')}")
    return orgs


def explore_org_publications(org_id, org_name, limit=5):
    """Get sample publications for an organization."""
    print(f"\n{'=' * 70}")
    print(f"PUBLICATIONS FOR: {org_name} (ID: {org_id})")
    print("=" * 70)
    data = api_get(f"/organizations/{org_id}/publications", params={"limit": limit})
    pubs = data.get("data", [])
    print(f"Sample of {len(pubs)} publications:\n")
    for pub in pubs:
        attrs = pub["attributes"]
        contributors = attrs.get("contributors", [])
        psu_authors = [c for c in contributors if c.get("psu_user_id")]
        print(f"  [{pub['id']}] {attrs['title'][:80]}...")
        print(f"       Type: {attrs.get('publication_type')} | Published: {attrs.get('published_on')}")
        print(f"       DOI: {attrs.get('doi', 'N/A')}")
        print(f"       Citations: {attrs.get('citation_count', 'N/A')}")
        print(f"       Contributors: {len(contributors)} total, {len(psu_authors)} PSU")
        if psu_authors:
            print(f"       PSU Authors: {', '.join(a['psu_user_id'] for a in psu_authors)}")
        tags = attrs.get("tags", [])
        if tags:
            top_tags = sorted(tags, key=lambda t: t.get("rank", 0), reverse=True)[:5]
            print(f"       Top Tags: {', '.join(t['name'] for t in top_tags)}")
        print()
    return pubs


def explore_user_profile(webaccess_id):
    """Get a user's public profile (no API key required)."""
    print(f"\n{'=' * 70}")
    print(f"USER PROFILE: {webaccess_id}")
    print("=" * 70)
    url = f"{BASE_URL}/users/{webaccess_id}/profile"
    resp = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
    if resp.status_code == 404:
        print(f"  User '{webaccess_id}' not found.")
        return None
    resp.raise_for_status()
    data = resp.json().get("data", {})
    attrs = data.get("attributes", {})
    print(f"  Name: {attrs.get('name')}")
    print(f"  Title: {attrs.get('title')}")
    print(f"  Organization: {attrs.get('organization_name')}")
    print(f"  Email: {attrs.get('email')}")
    print(f"  ORCID: {attrs.get('orcid_identifier')}")
    print(f"  Scopus Citations: {attrs.get('total_scopus_citations')}")
    print(f"  H-Index: {attrs.get('scopus_h_index')}")
    print(f"  Pure URL: {attrs.get('pure_profile_url')}")
    print(f"  Bio: {(attrs.get('bio') or '')[:200]}...")
    pubs = attrs.get("publications", [])
    print(f"  Publications count: {len(pubs)}")
    grants = attrs.get("grants", [])
    print(f"  Grants count: {len(grants)}")
    return data


def explore_user_publications(webaccess_id, limit=5):
    """Get publications for a specific user."""
    print(f"\n{'=' * 70}")
    print(f"PUBLICATIONS FOR USER: {webaccess_id}")
    print("=" * 70)
    data = api_get(f"/users/{webaccess_id}/publications",
                   params={"limit": limit, "order_first_by": "citation_count_desc"})
    pubs = data.get("data", [])
    print(f"Top {len(pubs)} publications by citation count:\n")
    for pub in pubs:
        attrs = pub["attributes"]
        print(f"  [{pub['id']}] {attrs['title'][:80]}")
        print(f"       Citations: {attrs.get('citation_count', 'N/A')} | {attrs.get('published_on', 'N/A')}")
        print(f"       Journal: {attrs.get('journal_title', 'N/A')}")
        print()
    return pubs


def explore_user_org_memberships(webaccess_id):
    """Get a user's organization memberships."""
    print(f"\n{'=' * 70}")
    print(f"ORGANIZATION MEMBERSHIPS: {webaccess_id}")
    print("=" * 70)
    data = api_get(f"/users/{webaccess_id}/organization_memberships")
    memberships = data.get("data", [])
    for m in memberships:
        attrs = m["attributes"]
        print(f"  {attrs.get('organization_name')}")
        print(f"       Type: {attrs.get('organization_type')} | Title: {attrs.get('position_title')}")
        print(f"       From: {attrs.get('position_started_on')} to {attrs.get('position_ended_on', 'present')}")
        print()
    return memberships


def explore_user_grants(webaccess_id):
    """Get a user's grants."""
    print(f"\n{'=' * 70}")
    print(f"GRANTS FOR USER: {webaccess_id}")
    print("=" * 70)
    data = api_get(f"/users/{webaccess_id}/grants")
    grants = data.get("data", [])
    print(f"Total grants: {len(grants)}\n")
    for g in grants[:5]:
        attrs = g["attributes"]
        print(f"  [{g['id']}] {(attrs.get('title') or 'Untitled')[:80]}")
        print(f"       Agency: {attrs.get('agency', 'N/A')}")
        print(f"       Amount: ${attrs.get('amount_in_dollars', 'N/A'):,}" if attrs.get('amount_in_dollars') else "       Amount: N/A")
        print(f"       Period: {attrs.get('start_date', 'N/A')} to {attrs.get('end_date', 'N/A')}")
        print()
    return grants


def explore_all_publications_sample(limit=5):
    """Get a sample of all publications in the system."""
    print(f"\n{'=' * 70}")
    print(f"ALL PUBLICATIONS SAMPLE (limit={limit})")
    print("=" * 70)
    data = api_get("/publications", params={"limit": limit})
    pubs = data.get("data", [])
    print(f"Retrieved {len(pubs)} publications\n")

    # Collect unique PSU user IDs from contributors
    all_psu_users = set()
    all_pub_types = set()
    for pub in pubs:
        attrs = pub["attributes"]
        all_pub_types.add(attrs.get("publication_type"))
        for c in attrs.get("contributors", []):
            if c.get("psu_user_id"):
                all_psu_users.add(c["psu_user_id"])

    print(f"  Unique PSU users found in sample: {len(all_psu_users)}")
    print(f"  PSU user IDs: {', '.join(sorted(all_psu_users))}")
    print(f"  Publication types: {', '.join(sorted(all_pub_types))}")
    return pubs, all_psu_users


def main():
    print("Penn State Researcher Metadata Database (RMD) API Explorer")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-8:]}")
    print()

    # 1. Explore organizations
    orgs = explore_organizations()

    # 2. Sample publications from first organization
    if orgs:
        first_org = orgs[0]
        explore_org_publications(
            first_org["id"],
            first_org["attributes"]["name"],
            limit=3
        )

    # 3. Get a sample of all publications and find PSU user IDs
    pubs, psu_users = explore_all_publications_sample(limit=10)

    # 4. Explore a specific user if we found any
    if psu_users:
        sample_user = sorted(psu_users)[0]
        explore_user_profile(sample_user)
        explore_user_publications(sample_user, limit=5)
        explore_user_org_memberships(sample_user)
        explore_user_grants(sample_user)


if __name__ == "__main__":
    main()
