"""
Data Processor Module
Handles loading and cleaning researcher data from Excel files.
"""

import pandas as pd
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_researchers(filepath: str) -> pd.DataFrame:
    """
    Load researcher data from Excel or CSV file and clean names.
    
    Args:
        filepath: Path to Excel (.xls, .xlsx) or CSV file containing researcher data
        
    Returns:
        DataFrame with cleaned researcher names
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    file_path = Path(filepath)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        logger.info(f"Loading researchers from {file_path}")
        
        # Determine file type and load accordingly
        if file_path.suffix.lower() in ['.xls', '.xlsx']:
            df = pd.read_excel(filepath)
        elif file_path.suffix.lower() == '.csv':
            df = pd.read_csv(filepath)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}. Use .xls, .xlsx, or .csv")
        
        if 'Name' not in df.columns:
            raise ValueError("File must contain a 'Name' column")
        
        # Clean names: remove credentials after comma (e.g., "John Doe, PhD" -> "John Doe")
        original_count = len(df)
        df['Name'] = df['Name'].str.split(',').str[0].str.strip()
        
        # Remove any rows with empty names
        df = df[df['Name'].notna() & (df['Name'] != '')]
        
        cleaned_count = len(df)
        logger.info(f"Loaded {cleaned_count} researchers (removed {original_count - cleaned_count} invalid entries)")
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading file: {e}")
        raise


def validate_researchers(df: pd.DataFrame) -> bool:
    """
    Validate researcher DataFrame.
    
    Args:
        df: DataFrame containing researcher data
        
    Returns:
        True if valid, False otherwise
    """
    if df is None or df.empty:
        logger.error("DataFrame is empty")
        return False
    
    if 'Name' not in df.columns:
        logger.error("DataFrame missing 'Name' column")
        return False
    
    # Check for duplicates
    duplicates = df[df.duplicated(subset=['Name'], keep=False)]
    if not duplicates.empty:
        duplicate_names = duplicates['Name'].unique().tolist()
        logger.warning(f"Found {len(duplicate_names)} duplicate names: {duplicate_names[:5]}")
    
    # Check for unusual characters or very short names
    unusual = df[df['Name'].str.len() < 3]
    if not unusual.empty:
        logger.warning(f"Found {len(unusual)} researchers with suspiciously short names")
    
    logger.info(f"Validation complete: {len(df)} researchers ready for processing")
    return True


def add_results_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add empty columns for storing API results.
    
    Args:
        df: DataFrame containing researcher data
        
    Returns:
        DataFrame with added result columns
    """
    df['publications_count'] = 0
    df['documents_count'] = 0
    df['status'] = 'pending'
    df['error'] = None
    
    return df