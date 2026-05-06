import json
import os

INPUT_FILE = "keep/openalex_exports/psu_researchers.json"
OUTPUT_FILE = "keep/openalex_exports/psu_social_science_2025.json"

def filter_researchers():
    """
    Filter PSU researchers to those who:
    1. Have 2025 in their affiliation years (currently affiliated)
    2. Are in the Social Sciences domain
    """
    print(f"Reading researchers from {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        researchers = json.load(f)

    print(f"Total researchers: {len(researchers):,}")

    filtered = []

    for researcher in researchers:
        # Check for 2025 affiliation
        psu_aff = researcher.get("psu_affiliation") or {}
        years = psu_aff.get("years", [])
        if 2025 not in years:
            continue

        # Check for Social Sciences domain
        field = researcher.get("field_of_research") or {}
        domain = field.get("domain", "")
        if domain != "Social Sciences":
            continue

        filtered.append(researcher)

    print(f"Filtered researchers (2025 + Social Sciences): {len(filtered):,}")

    # Show breakdown by field
    fields = {}
    for r in filtered:
        field_name = r.get("field_of_research", {}).get("field", "Unknown")
        fields[field_name] = fields.get(field_name, 0) + 1

    print("\nBreakdown by field:")
    for field_name, count in sorted(fields.items(), key=lambda x: -x[1]):
        print(f"  {field_name}: {count}")

    # Save filtered dataset
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {OUTPUT_FILE}")

    # Show sample
    if filtered:
        print("\nSample researcher:")
        sample = filtered[0]
        print(f"  Name: {sample.get('display_name')}")
        print(f"  ORCID: {sample.get('orcid')}")
        print(f"  Field: {sample.get('field_of_research', {}).get('field')}")
        print(f"  Topic: {sample.get('field_of_research', {}).get('topic')}")

if __name__ == "__main__":
    filter_researchers()
