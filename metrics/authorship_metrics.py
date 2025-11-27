"""
Authorship Metric Extractors
Analyze authorship position and patterns in publications.
"""

from typing import Dict, Optional
from metrics.base_extractor import MetricExtractor


class FirstAuthorCountExtractor(MetricExtractor):
    """Count how many publications where researcher was first author."""
    
    @property
    def metric_name(self) -> str:
        return "first_author_count"
    
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
        Count publications where researcher is first author.
        
        Args:
            publications_response: Full JSON from publications endpoint
            documents_response: Not used
            researcher_name: Name of researcher to match
            
        Returns:
            int: Number of first-author publications
        """
        if not publications_response or not researcher_name:
            return 0
        
        count = 0
        results = publications_response.get('results', {}).get('results', [])
        
        # Create name variants for matching
        name_variants = self._get_name_variants(researcher_name)
        
        for pub in results:
            authors = pub.get('authors', [])
            if authors:
                # Check if first author matches researcher
                first_author = authors[0].lower()
                if any(variant in first_author for variant in name_variants):
                    count += 1
        
        return count
    
    def _get_name_variants(self, name: str) -> list:
        """
        Generate possible name variants for matching.
        
        Args:
            name: Full researcher name
            
        Returns:
            List of lowercase name variants
        """
        name_lower = name.lower()
        variants = [name_lower]
        
        # Handle different name formats
        parts = name_lower.split()
        if len(parts) >= 2:
            # Add "Last, First" format
            variants.append(f"{parts[-1]}, {parts[0]}")
            # Add "First Last" format
            variants.append(f"{parts[0]} {parts[-1]}")
        
        return variants


class SecondAuthorCountExtractor(MetricExtractor):
    """Count how many publications where researcher was second author."""
    
    @property
    def metric_name(self) -> str:
        return "second_author_count"
    
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
        Count publications where researcher is second author.
        
        Args:
            publications_response: Full JSON from publications endpoint
            documents_response: Not used
            researcher_name: Name of researcher to match
            
        Returns:
            int: Number of second-author publications
        """
        if not publications_response or not researcher_name:
            return 0
        
        count = 0
        results = publications_response.get('results', {}).get('results', [])
        
        # Create name variants for matching
        name_variants = self._get_name_variants(researcher_name)
        
        for pub in results:
            authors = pub.get('authors', [])
            # Need at least 2 authors for second author position
            if len(authors) >= 2:
                # Check if second author (index 1) matches researcher
                second_author = authors[1].lower()
                if any(variant in second_author for variant in name_variants):
                    count += 1
        
        return count
    
    def _get_name_variants(self, name: str) -> list:
        """
        Generate possible name variants for matching.
        
        Args:
            name: Full researcher name
            
        Returns:
            List of lowercase name variants
        """
        name_lower = name.lower()
        variants = [name_lower]
        
        # Handle different name formats
        parts = name_lower.split()
        if len(parts) >= 2:
            # Add "Last, First" format
            variants.append(f"{parts[-1]}, {parts[0]}")
            # Add "First Last" format
            variants.append(f"{parts[0]} {parts[-1]}")
        
        return variants


class LastAuthorCountExtractor(MetricExtractor):
    """Count how many publications where researcher was last author (often senior author)."""
    
    @property
    def metric_name(self) -> str:
        return "last_author_count"
    
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
        Count publications where researcher is last author.
        
        Last author position is often the senior/principal investigator position.
        
        Args:
            publications_response: Full JSON from publications endpoint
            documents_response: Not used
            researcher_name: Name of researcher to match
            
        Returns:
            int: Number of last-author publications
        """
        if not publications_response or not researcher_name:
            return 0
        
        count = 0
        results = publications_response.get('results', {}).get('results', [])
        
        # Create name variants for matching
        name_variants = self._get_name_variants(researcher_name)
        
        for pub in results:
            authors = pub.get('authors', [])
            # Need at least 2 authors for meaningful last author position
            if len(authors) >= 2:
                # Check if last author matches researcher
                last_author = authors[-1].lower()
                if any(variant in last_author for variant in name_variants):
                    count += 1
        
        return count
    
    def _get_name_variants(self, name: str) -> list:
        """Generate possible name variants for matching."""
        name_lower = name.lower()
        variants = [name_lower]
        
        parts = name_lower.split()
        if len(parts) >= 2:
            variants.append(f"{parts[-1]}, {parts[0]}")
            variants.append(f"{parts[0]} {parts[-1]}")
        
        return variants


class AverageAuthorPositionExtractor(MetricExtractor):
    """Calculate average author position across all publications (1.0 = always first)."""
    
    @property
    def metric_name(self) -> str:
        return "avg_author_position"
    
    @property
    def requires_publications(self) -> bool:
        return True
    
    @property
    def requires_documents(self) -> bool:
        return False
    
    def extract(self, publications_response: Optional[Dict], 
                documents_response: Optional[Dict],
                researcher_name: str = "") -> Optional[float]:
        """
        Calculate average author position (1.0 = first, 2.0 = second, etc.).
        
        Args:
            publications_response: Full JSON from publications endpoint
            documents_response: Not used
            researcher_name: Name of researcher to match
            
        Returns:
            float: Average position, or None if no publications found
        """
        if not publications_response or not researcher_name:
            return None
        
        positions = []
        results = publications_response.get('results', {}).get('results', [])
        
        # Create name variants for matching
        name_variants = self._get_name_variants(researcher_name)
        
        for pub in results:
            authors = pub.get('authors', [])
            # Find researcher's position in author list
            for idx, author in enumerate(authors):
                author_lower = author.lower()
                if any(variant in author_lower for variant in name_variants):
                    positions.append(idx + 1)  # Convert to 1-based position
                    break  # Found match, move to next publication
        
        if not positions:
            return None
        
        return round(sum(positions) / len(positions), 2)
    
    def _get_name_variants(self, name: str) -> list:
        """Generate possible name variants for matching."""
        name_lower = name.lower()
        variants = [name_lower]
        
        parts = name_lower.split()
        if len(parts) >= 2:
            variants.append(f"{parts[-1]}, {parts[0]}")
            variants.append(f"{parts[0]} {parts[-1]}")
        
        return variants