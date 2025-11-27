#!/usr/bin/env python3
"""
Quick test script to verify metric system works.
"""

from metrics.registry import registry

# Initialize registry
registry.initialize_default_extractors()

# List all metrics
print("\n" + "="*60)
print("TESTING METRIC SYSTEM")
print("="*60)

print("\nAvailable metrics:")
for metric in registry.list_available_metrics():
    print(f"  - {metric}")

print(f"\nTotal: {len(registry.list_available_metrics())} metrics")

print("\nDetailed info:")
print(f"{'Metric':<30} {'Requires Pubs':<15} {'Requires Docs'}")
print("-" * 60)
for info in registry.get_metrics_info():
    print(f"{info['name']:<30} {str(info['requires_publications']):<15} {str(info['requires_documents'])}")

# Test extracting from sample data
print("\n" + "="*60)
print("TESTING EXTRACTION")
print("="*60)

# Sample API responses (from your psu_publications_data.json and psu_documents_data.json)
sample_pub_response = {
    'query': {'total_results': 1},
    'results': {'results': []}
}

sample_doc_response = {
    'query': {'total_results': 12},
    'results': [
        {'source': {'country': 'USA', 'type': 'think tank'}},
        {'source': {'country': 'USA', 'type': 'government'}},
        {'source': {'country': 'IGO', 'type': 'igo'}},
        {'source': {'country': 'NOR', 'type': 'government'}},
    ]
}

# Test each extractor
extractors = registry.get_extractors()
print(f"\nTesting {len(extractors)} extractors:\n")

for extractor in extractors:
    try:
        value = extractor.extract(sample_pub_response, sample_doc_response, "Test Researcher")
        print(f"{extractor.metric_name:<30} = {value}")
    except Exception as e:
        print(f"{extractor.metric_name:<30} ERROR: {e}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60 + "\n")