"""
Country Metric Extractors
Geographic analysis metrics for policy document citations.
"""

from typing import Dict, Optional
from metrics.base_extractor import MetricExtractor


class CitationCountriesExtractor(MetricExtractor):
    """Extract list of countries where researcher's work is cited in policy documents."""
    
    @property
    def metric_name(self) -> str:
        return "citation_countries"
    
    @property
    def requires_publications(self) -> bool:
        return False
    
    @property
    def requires_documents(self) -> bool:
        return True
    
    def extract(self, publications_response: Optional[Dict], 
                documents_response: Optional[Dict],
                researcher_name: str = "") -> Optional[str]:
        """
        Extract comma-separated list of countries citing the work.
        
        Args:
            publications_response: Not used
            documents_response: Full JSON from documents endpoint
            researcher_name: Not used
            
        Returns:
            str: Comma-separated country list or None if no citations
        """
        if not documents_response:
            return None
        
        countries = set()
        results = documents_response.get('results', [])
        
        for doc in results:
            country = doc.get('source', {}).get('country')
            if country:
                countries.add(country)
        
        if not countries:
            return None
        
        # Sort for consistent output
        return ', '.join(sorted(countries))


class UniqueCountryCountExtractor(MetricExtractor):
    """Count unique countries citing the researcher's work (excluding IGOs)."""
    
    @property
    def metric_name(self) -> str:
        return "unique_country_count"
    
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
        Count unique countries citing the work.
        
        IGOs (International Governmental Organizations) are excluded from the count
        as they represent international bodies rather than specific countries.
        
        Args:
            publications_response: Not used
            documents_response: Full JSON from documents endpoint
            researcher_name: Not used
            
        Returns:
            int: Number of unique countries
        """
        if not documents_response:
            return 0
        
        countries = set()
        results = documents_response.get('results', [])
        
        for doc in results:
            country = doc.get('source', {}).get('country')
            # Exclude IGO as it's not a country
            if country and country != 'IGO':
                countries.add(country)
        
        return len(countries)


class GovernmentCitationCountExtractor(MetricExtractor):
    """Count citations from government policy documents."""
    
    @property
    def metric_name(self) -> str:
        return "government_citations"
    
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
        Count citations from government policy documents.
        
        Args:
            publications_response: Not used
            documents_response: Full JSON from documents endpoint
            researcher_name: Not used
            
        Returns:
            int: Number of government citations
        """
        if not documents_response:
            return 0
        
        count = 0
        results = documents_response.get('results', [])
        
        for doc in results:
            source_type = doc.get('source', {}).get('type', '').lower()
            if source_type == 'government':
                count += 1
        
        return count


class IGOCitationCountExtractor(MetricExtractor):
    """Count citations from International Governmental Organizations."""
    
    @property
    def metric_name(self) -> str:
        return "igo_citations"
    
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
        Count citations from IGO policy documents.
        
        Args:
            publications_response: Not used
            documents_response: Full JSON from documents endpoint
            researcher_name: Not used
            
        Returns:
            int: Number of IGO citations
        """
        if not documents_response:
            return 0
        
        count = 0
        results = documents_response.get('results', [])
        
        for doc in results:
            source_type = doc.get('source', {}).get('type', '').lower()
            if source_type == 'igo':
                count += 1
        
        return count