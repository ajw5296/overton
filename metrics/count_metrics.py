"""
Count Metric Extractors
Basic count metrics for publications and documents.
"""

from typing import Dict, Optional
from metrics.base_extractor import MetricExtractor


class PublicationCountExtractor(MetricExtractor):
    """Extract the total count of publications."""
    
    @property
    def metric_name(self) -> str:
        return "publications_count"
    
    @property
    def requires_publications(self) -> bool:
        return True
    
    @property
    def requires_documents(self) -> bool:
        return False
    
    def extract(self, publications_response: Optional[Dict], 
                documents_response: Optional[Dict],
                researcher_name: str = "") -> int:
        """
        Extract publication count from API response.
        
        Args:
            publications_response: Full JSON from publications endpoint
            documents_response: Not used
            researcher_name: Not used
            
        Returns:
            int: Number of publications
        """
        if not publications_response:
            return 0
        
        return publications_response.get('query', {}).get('total_results', 0)


class DocumentCountExtractor(MetricExtractor):
    """Extract the total count of policy documents."""
    
    @property
    def metric_name(self) -> str:
        return "documents_count"
    
    @property
    def requires_publications(self) -> bool:
        return False
    
    @property
    def requires_documents(self) -> bool:
        return True
    
    def extract(self, publications_response: Optional[Dict], 
                documents_response: Optional[Dict],
                researcher_name: str = "") -> int:
        """
        Extract document count from API response.
        
        Args:
            publications_response: Not used
            documents_response: Full JSON from documents endpoint
            researcher_name: Not used
            
        Returns:
            int: Number of policy documents
        """
        if not documents_response:
            return 0
        
        return documents_response.get('query', {}).get('total_results', 0)