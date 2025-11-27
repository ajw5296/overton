# Overton Metrics Framework Guide

## Overview

The Overton Researcher Tracker now features a flexible, plugin-based metric extraction system that makes it easy to extract custom metrics from Overton API data without modifying core code.

## Quick Start

### List Available Metrics

```bash
python main.py --list-metrics
```

### Extract Specific Metrics

```bash
# Extract just publication and document counts
python main.py --input data.xls --output results.csv --api-key YOUR_KEY \
    --metrics publications_count documents_count

# Extract country-based metrics
python main.py --input data.xls --output results.csv --api-key YOUR_KEY \
    --metrics citation_countries unique_country_count government_citations

# Extract ALL available metrics
python main.py --input data.xls --output results.csv --api-key YOUR_KEY
```

## Currently Available Metrics

### Count Metrics (`metrics/count_metrics.py`)

| Metric | Description | Requires Pubs | Requires Docs |
|--------|-------------|---------------|---------------|
| `publications_count` | Total number of publications | ✓ | |
| `documents_count` | Total number of policy documents | | ✓ |

### Country Metrics (`metrics/country_metrics.py`)

| Metric | Description | Requires Pubs | Requires Docs |
|--------|-------------|---------------|---------------|
| `citation_countries` | Comma-separated list of countries citing the work | | ✓ |
| `unique_country_count` | Number of unique countries (excluding IGOs) | | ✓ |
| `government_citations` | Count of citations from government sources | | ✓ |
| `igo_citations` | Count of citations from International Governmental Organizations | | ✓ |

## Example Output

### Basic Counts
```csv
Name,publications_count,documents_count,status,error,processed_at
Yubraj Acharya,13,61,success,,2025-11-26T12:14:41.428767
Lee Ahern,6,13,success,,2025-11-26T12:14:45.945018
```

### With Country Metrics
```csv
Name,citation_countries,unique_country_count,government_citations,igo_citations,status
Yubraj Acharya,"France, Germany, IGO, Kenya, South Africa, USA",5,3,42,success
Lee Ahern,"Australia, Estonia, Germany, IGO, Sweden, USA",5,6,3,success
```

## Architecture

### How It Works

1. **API Client** - Makes API calls and returns full JSON responses
2. **Metric Extractors** - Plugin classes that process JSON and extract specific metrics
3. **Registry** - Central system that manages available extractors
4. **Main Script** - Orchestrates the extraction process

```
Researcher Data → API Client → Full JSON Response → Metric Extractors → CSV Output
```

### Key Benefits

✅ **Efficient** - Only makes necessary API calls based on selected metrics  
✅ **Extensible** - Add new metrics without touching core code  
✅ **Flexible** - Choose which metrics to extract per run  
✅ **Backwards Compatible** - Original count-only workflow still works  
✅ **Table-Friendly** - Everything becomes CSV columns for easy analysis

## Creating Custom Metrics

### Step 1: Create a New Extractor Class

Create a new file in the `metrics/` directory (or add to an existing one):

```python
# metrics/my_metrics.py
from typing import Dict, Optional
from metrics.base_extractor import MetricExtractor

class MyCustomMetric(MetricExtractor):
    """Description of what this metric extracts."""
    
    @property
    def metric_name(self) -> str:
        return "my_metric_name"  # Column name in CSV
    
    @property
    def requires_publications(self) -> bool:
        return True  # Set to True if you need publications data
    
    @property
    def requires_documents(self) -> bool:
        return False  # Set to True if you need documents data
    
    def extract(self, publications_response: Optional[Dict], 
                documents_response: Optional[Dict],
                researcher_name: str = "") -> any:
        """
        Extract your metric from the API responses.
        
        Returns:
            The extracted value (int, str, float, list, etc.)
        """
        # Your extraction logic here
        # Access data like: publications_response['results']['results']
        # or: documents_response['results']
        
        return calculated_value
```

### Step 2: Register Your Extractor

Add your extractor to the registry in `metrics/registry.py`:

```python
def initialize_default_extractors(self) -> None:
    # ... existing imports ...
    from metrics.my_metrics import MyCustomMetric
    
    # ... existing registrations ...
    self.register(MyCustomMetric)
```

### Step 3: Use Your New Metric

```bash
python main.py --input data.xls --output results.csv --api-key KEY \
    --metrics my_metric_name
```

## Advanced Examples

### Multi-Column Extractor

Some metrics create multiple columns:

```python
class TopicBreakdownExtractor(MetricExtractor):
    @property
    def metric_name(self) -> str:
        return "topic_breakdown"
    
    def get_column_names(self) -> List[str]:
        # Override to specify multiple columns
        return ['top_topic_1', 'top_topic_2', 'top_topic_3']
    
    def extract(self, pubs_response, docs_response, name=""):
        # Return a dict with keys matching column names
        topics = self._extract_topics(docs_response)
        return {
            'top_topic_1': topics[0] if len(topics) > 0 else None,
            'top_topic_2': topics[1] if len(topics) > 1 else None,
            'top_topic_3': topics[2] if len(topics) > 2 else None,
        }
```

### Context-Aware Extractor

Use the researcher name for advanced processing:

```python
class FirstAuthorCountExtractor(MetricExtractor):
    def extract(self, pubs_response, docs_response, researcher_name=""):
        count = 0
        results = pubs_response.get('results', {}).get('results', [])
        
        for pub in results:
            authors = pub.get('authors', [])
            if authors:
                # Check if researcher is first author
                first_author = authors[0].lower()
                if researcher_name.lower() in first_author:
                    count += 1
        
        return count
```

## API Response Structure

### Publications Endpoint Response

```python
{
    'query': {
        'total_results': 13,
        'pages': 1,
        ...
    },
    'results': {
        'results': [
            {
                'title': '...',
                'doi': '...',
                'authors': ['Name 1', 'Name 2'],
                'citations': 12,
                'published_on': '2020-05-18',
                ...
            }
        ]
    }
}
```

### Documents Endpoint Response

```python
{
    'query': {
        'total_results': 61,
        'pages': 1,
        ...
    },
    'results': [
        {
            'policy_document_id': '...',
            'title': '...',
            'source': {
                'country': 'USA',
                'type': 'government',
                ...
            },
            'topics': ['Topic 1', 'Topic 2'],
            'published_on': '2022-05-18',
            ...
        }
    ]
}
```

## Performance Tips

### Optimize API Calls

- Only select metrics you need to minimize API calls
- Publications metrics require one API call per researcher
- Documents metrics require one API call per researcher
- Selecting both types requires two API calls per researcher

```bash
# Faster: Only documents metrics (1 call per researcher)
python main.py --input data.xls --output results.csv --api-key KEY \
    --metrics citation_countries unique_country_count

# Slower: Both types (2 calls per researcher)
python main.py --input data.xls --output results.csv --api-key KEY \
    --metrics publications_count citation_countries
```

### Rate Limiting

Use `--delay` to control request spacing:

```bash
# Wait 2 seconds between requests (slower but safer)
python main.py --input data.xls --output results.csv --api-key KEY --delay 2.0

# Faster but may hit rate limits
python main.py --input data.xls --output results.csv --api-key KEY --delay 0.5
```

## Future Metrics (Coming Soon)

### Impact Metrics
- Total citation count across all publications
- Average citations per publication
- h-index calculation
- Policy impact score (custom formula)

### Authorship Metrics
- First author percentage
- Last author percentage
- Average author position
- Co-author network size

### Topic Metrics
- Top research topics
- Policy area classifications
- SDG (Sustainable Development Goals) categories
- Most frequent keywords

### Temporal Metrics
- Publications per year
- Citation trends over time
- Recent vs historical impact

## Troubleshooting

### "Metric not found in registry"

Make sure your metric is registered in `metrics/registry.py`:

```python
self.register(YourMetricClass)
```

### "No valid extractors found"

Check that metric names are spelled correctly:

```bash
# List all available metrics
python main.py --list-metrics
```

### Import Errors

Make sure the `metrics/` directory has an `__init__.py` file.

## Contributing New Metrics

We welcome contributions! To add a new metric:

1. Create your extractor class following the pattern above
2. Add comprehensive docstrings
3. Register it in the registry
4. Test with sample data
5. Update this guide with your new metric

## Questions?

- Check the examples in `metrics/count_metrics.py` and `metrics/country_metrics.py`
- Run `python test_metrics.py` to see extractors in action
- Review the base class documentation in `metrics/base_extractor.py`