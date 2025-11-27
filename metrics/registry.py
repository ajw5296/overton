"""
Metric Registry
Central registry for managing available metric extractors.
"""

import logging
from typing import List, Type, Optional, Dict
from metrics.base_extractor import MetricExtractor

logger = logging.getLogger(__name__)


class MetricRegistry:
    """Central registry of available metric extractors."""
    
    def __init__(self):
        """Initialize the registry."""
        self._extractors: Dict[str, MetricExtractor] = {}
        self._initialized = False
    
    def register(self, extractor_class: Type[MetricExtractor]) -> None:
        """
        Register a metric extractor class.
        
        Args:
            extractor_class: Class (not instance) of MetricExtractor
        """
        try:
            # Instantiate the extractor
            instance = extractor_class()
            
            # Check if metric name already registered
            if instance.metric_name in self._extractors:
                logger.warning(
                    f"Metric '{instance.metric_name}' already registered, "
                    f"overwriting with {extractor_class.__name__}"
                )
            
            self._extractors[instance.metric_name] = instance
            logger.debug(f"Registered metric extractor: {instance.metric_name}")
            
        except Exception as e:
            logger.error(f"Failed to register {extractor_class.__name__}: {e}")
    
    def get_extractor(self, metric_name: str) -> Optional[MetricExtractor]:
        """
        Get a specific extractor by metric name.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            MetricExtractor instance or None if not found
        """
        return self._extractors.get(metric_name)
    
    def get_extractors(self, metric_names: Optional[List[str]] = None) -> List[MetricExtractor]:
        """
        Get extractors by name, or all extractors if None.
        
        Args:
            metric_names: List of metric names to retrieve, or None for all
            
        Returns:
            List of MetricExtractor instances
        """
        if metric_names is None:
            return list(self._extractors.values())
        
        extractors = []
        for name in metric_names:
            extractor = self._extractors.get(name)
            if extractor:
                extractors.append(extractor)
            else:
                logger.warning(f"Metric '{name}' not found in registry")
        
        return extractors
    
    def list_available_metrics(self) -> List[str]:
        """
        List all available metric names.
        
        Returns:
            List of metric names
        """
        return sorted(self._extractors.keys())
    
    def get_metrics_info(self) -> List[Dict[str, str]]:
        """
        Get detailed information about all registered metrics.
        
        Returns:
            List of dicts with metric information
        """
        info = []
        for name, extractor in sorted(self._extractors.items()):
            info.append({
                'name': name,
                'class': extractor.__class__.__name__,
                'requires_publications': extractor.requires_publications,
                'requires_documents': extractor.requires_documents,
                'columns': ', '.join(extractor.get_column_names())
            })
        return info
    
    def initialize_default_extractors(self) -> None:
        """
        Register all default metric extractors.
        
        This method should be called once to populate the registry
        with all built-in extractors.
        """
        if self._initialized:
            logger.debug("Registry already initialized")
            return
        
        # Import and register all default extractors
        from metrics.count_metrics import (
            PublicationCountExtractor,
            DocumentCountExtractor
        )
        from metrics.country_metrics import (
            CitationCountriesExtractor,
            UniqueCountryCountExtractor,
            GovernmentCitationCountExtractor,
            IGOCitationCountExtractor
        )
        from metrics.authorship_metrics import (
            FirstAuthorCountExtractor,
            SecondAuthorCountExtractor,
            LastAuthorCountExtractor,
            AverageAuthorPositionExtractor
        )
        
        # Register count metrics
        self.register(PublicationCountExtractor)
        self.register(DocumentCountExtractor)
        
        # Register country metrics
        self.register(CitationCountriesExtractor)
        self.register(UniqueCountryCountExtractor)
        self.register(GovernmentCitationCountExtractor)
        self.register(IGOCitationCountExtractor)
        
        # Register authorship metrics
        self.register(FirstAuthorCountExtractor)
        self.register(SecondAuthorCountExtractor)
        self.register(LastAuthorCountExtractor)
        self.register(AverageAuthorPositionExtractor)
        
        self._initialized = True
        logger.info(f"Registry initialized with {len(self._extractors)} extractors")
    
    def __repr__(self) -> str:
        """String representation of the registry."""
        return f"MetricRegistry(metrics={len(self._extractors)})"


# Global registry instance
registry = MetricRegistry()