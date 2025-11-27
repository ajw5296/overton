"""
Base Metric Extractor
Abstract base class for all metric extractors.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class MetricExtractor(ABC):
    """Base class for all metric extractors."""
    
    @property
    @abstractmethod
    def metric_name(self) -> str:
        """
        Name of the metric (will become column name in output).
        
        Returns:
            str: Metric name (e.g., 'publications_count', 'citation_countries')
        """
        pass
    
    @property
    @abstractmethod
    def requires_publications(self) -> bool:
        """
        Does this metric need publications API data?
        
        Returns:
            bool: True if publications endpoint is needed
        """
        pass
    
    @property
    @abstractmethod
    def requires_documents(self) -> bool:
        """
        Does this metric need documents API data?
        
        Returns:
            bool: True if documents endpoint is needed
        """
        pass
    
    @abstractmethod
    def extract(self, publications_response: Optional[Dict], 
                documents_response: Optional[Dict], 
                researcher_name: str = "") -> Any:
        """
        Extract metric value from API responses.
        
        Args:
            publications_response: Full JSON response from publications endpoint
            documents_response: Full JSON response from documents endpoint
            researcher_name: Name of researcher (for context-aware extraction)
            
        Returns:
            Extracted metric value. Can be:
                - Simple types (int, str, float, bool)
                - Lists or tuples for multi-value metrics
                - Dict for extractors that create multiple columns
        """
        pass
    
    def get_column_names(self) -> List[str]:
        """
        Return list of column names this extractor creates.
        
        Override this method if the extractor creates multiple columns.
        Default behavior returns a single column with metric_name.
        
        Returns:
            List[str]: Column names
        """
        return [self.metric_name]
    
    def format_output(self, value: Any) -> Any:
        """
        Format the extracted value for CSV output.
        
        Override this method for custom formatting.
        Default behavior returns value as-is.
        
        Args:
            value: Extracted value
            
        Returns:
            Formatted value suitable for CSV
        """
        return value
    
    def __repr__(self) -> str:
        """String representation of the extractor."""
        return f"{self.__class__.__name__}(metric_name='{self.metric_name}')"