"""
Overton API Client
Handles all interactions with the Overton API with retry logic and error handling.
"""

import requests
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class OvertonAPIClient:
    """Client for interacting with the Overton API."""
    
    DOCUMENTS_URL = "https://app.overton.io/documents.php"
    PUBLICATIONS_URL = "https://app.overton.io/articles.php"
    ARTICLES_URL = "https://app.overton.io/articles.php"
    
    def __init__(self, api_key: str, delay: float = 0.5, max_retries: int = 3, timeout: int = 30):
        """
        Initialize the Overton API client.
        
        Args:
            api_key: Overton API key
            delay: Seconds to wait between requests (rate limiting)
            max_retries: Maximum number of retry attempts for failed requests
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.delay = delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.last_request_time = 0
        
    def query_publications(self, institution: str, name: str) -> Dict:
        """
        Query the publications endpoint for a researcher.
        
        Args:
            institution: Institution name (e.g., "Pennsylvania State University")
            name: Researcher name
            
        Returns:
            Dict with:
                - 'total_results' (int): Count of publications
                - 'full_response' (dict): Complete API JSON response
                - 'error' (str or None): Error message if request failed
        """
        query_string = self._build_query_string(institution, name)
        params = {
            "format": "json",
            "page": 1,
            "open_institution_authors": query_string,
            "api_key": self.api_key
        }
        
        response = self._make_request(self.PUBLICATIONS_URL, params)
        return self._extract_results(response, name, "publications")
    
    def query_documents(self, institution: str, name: str) -> Dict:
        """
        Query the documents endpoint for a researcher.
        
        Args:
            institution: Institution name (e.g., "Pennsylvania State University")
            name: Researcher name
            
        Returns:
            Dict with:
                - 'total_results' (int): Count of documents
                - 'full_response' (dict): Complete API JSON response
                - 'error' (str or None): Error message if request failed
        """
        query_string = self._build_query_string(institution, name)
        params = {
            "format": "json",
            "page": 1,
            "open_linked_institution_authors": query_string,
            "api_key": self.api_key
        }
        
        response = self._make_request(self.DOCUMENTS_URL, params)
        return self._extract_results(response, name, "documents")

    def query_by_doi(self, doi: str) -> Dict:
        """
        Query the articles endpoint by DOI.

        Args:
            doi: The DOI of the article.

        Returns:
            Dict with API response data or an error message.
        """
        params = {
            "format": "json",
            "query": doi,
            "api_key": self.api_key
        }
        
        response = self._make_request(self.ARTICLES_URL, params)
        return self._extract_results(response, doi, "DOI")
    
    def _build_query_string(self, institution: str, name: str) -> str:
        """
        Build the query string in Overton's required format.
        
        Format: "Institution __OVSEP__ Name __OVSEP__ lowercase name"
        
        Args:
            institution: Institution name
            name: Researcher name
            
        Returns:
            Formatted query string
        """
        return f"{institution} __OVSEP__ {name} __OVSEP__ {name.lower()}"
    
    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        Make an API request with retry logic and rate limiting.
        
        Args:
            endpoint: API endpoint URL
            params: Request parameters
            
        Returns:
            Response JSON dict or None if all retries failed
        """
        # Rate limiting: ensure minimum delay between requests
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Making request to {endpoint} (attempt {attempt + 1}/{self.max_retries})")
                
                response = requests.get(endpoint, params=params, timeout=self.timeout)
                self.last_request_time = time.time()
                
                # Check for rate limiting
                if response.status_code == 429:
                    logger.warning(f"Rate limited (429), waiting 60 seconds before retry")
                    time.sleep(60)
                    continue
                
                # Check for server errors (retry)
                if response.status_code >= 500:
                    logger.warning(f"Server error {response.status_code}, retrying...")
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                
                # Check for client errors (don't retry)
                if response.status_code >= 400:
                    logger.error(f"Client error {response.status_code}: {response.text[:200]}")
                    return None
                
                # Success
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error: {e} (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    
            except requests.exceptions.JSONDecodeError:
                logger.error("Invalid JSON response from API")
                return None
                
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return None
        
        logger.error(f"All {self.max_retries} retry attempts failed")
        return None
    
    def _extract_results(self, response: Optional[Dict], name: str, endpoint_type: str) -> Dict:
        """
        Extract total_results and full response from API response.
        
        Args:
            response: API response JSON
            name: Researcher name (for logging)
            endpoint_type: "publications" or "documents"
            
        Returns:
            Dict with 'total_results', 'full_response', and 'error'
        """
        if response is None:
            return {
                'total_results': 0,
                'full_response': {},
                'error': f'API request failed after {self.max_retries} attempts'
            }
        
        try:
            total = response.get('query', {}).get('total_results', 0)
            logger.info(f"[{name}] {endpoint_type}: {total} results")
            return {
                'total_results': total,
                'full_response': response,
                'error': None
            }
        except (KeyError, AttributeError) as e:
            logger.error(f"Error extracting results for {name}: {e}")
            return {
                'total_results': 0,
                'full_response': {},
                'error': f'Invalid response structure: {str(e)}'
            }