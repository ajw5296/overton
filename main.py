#!/usr/bin/env python3
"""
Overton Researcher Tracker
Main script for querying Overton API for Penn State researchers.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm

from data_processor import load_researchers, validate_researchers, add_results_columns
from api_client import OvertonAPIClient


def setup_logging(log_level: str = "INFO"):
    """Configure logging for the application."""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('overton_tracker.log')
        ]
    )


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Query Overton API for Penn State researcher publications and policy documents.'
    )
    
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Path to Excel file containing researcher names'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Path for output CSV file'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        required=True,
        help='Overton API key'
    )
    
    parser.add_argument(
        '--institution',
        type=str,
        default='Pennsylvania State University',
        help='Institution name (default: Pennsylvania State University)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay between API requests in seconds (default: 0.5)'
    )
    
    parser.add_argument(
        '--retry',
        type=int,
        default=3,
        help='Maximum retry attempts for failed requests (default: 3)'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    return parser.parse_args()


def process_researchers(df: pd.DataFrame, client: OvertonAPIClient, institution: str):
    """
    Process all researchers and query the Overton API.
    
    Args:
        df: DataFrame containing researcher data
        client: OvertonAPIClient instance
        institution: Institution name
        
    Returns:
        DataFrame with results
    """
    logger = logging.getLogger(__name__)
    results = []
    
    # Progress bar
    with tqdm(total=len(df), desc="Processing researchers", unit="researcher") as pbar:
        for idx, row in df.iterrows():
            name = row['Name']
            pbar.set_description(f"Processing: {name[:30]}")
            
            # Query publications endpoint
            pub_result = client.query_publications(institution, name)
            
            # Query documents endpoint
            doc_result = client.query_documents(institution, name)
            
            # Determine overall status
            if pub_result['error'] or doc_result['error']:
                status = 'error'
                error_msg = pub_result['error'] or doc_result['error']
            else:
                status = 'success'
                error_msg = None
            
            # Store results
            results.append({
                'Name': name,
                'publications_count': pub_result['total_results'],
                'documents_count': doc_result['total_results'],
                'status': status,
                'error': error_msg,
                'processed_at': datetime.now().isoformat()
            })
            
            pbar.update(1)
    
    return pd.DataFrame(results)


def print_summary(results_df: pd.DataFrame):
    """Print summary statistics."""
    logger = logging.getLogger(__name__)
    
    total = len(results_df)
    successful = len(results_df[results_df['status'] == 'success'])
    errors = len(results_df[results_df['status'] == 'error'])
    
    total_pubs = results_df['publications_count'].sum()
    total_docs = results_df['documents_count'].sum()
    avg_pubs = results_df['publications_count'].mean()
    avg_docs = results_df['documents_count'].mean()
    
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Total researchers processed: {total}")
    print(f"Successful queries: {successful} ({successful/total*100:.1f}%)")
    print(f"Failed queries: {errors} ({errors/total*100:.1f}%)")
    print(f"\nTotal publications found: {total_pubs}")
    print(f"Total policy documents found: {total_docs}")
    print(f"Average publications per researcher: {avg_pubs:.1f}")
    print(f"Average documents per researcher: {avg_docs:.1f}")
    
    # Top researchers
    print(f"\nTop 5 researchers by publications:")
    top_pubs = results_df.nlargest(5, 'publications_count')[['Name', 'publications_count']]
    for idx, row in top_pubs.iterrows():
        print(f"  {row['Name']}: {row['publications_count']}")
    
    print(f"\nTop 5 researchers by policy documents:")
    top_docs = results_df.nlargest(5, 'documents_count')[['Name', 'documents_count']]
    for idx, row in top_docs.iterrows():
        print(f"  {row['Name']}: {row['documents_count']}")
    
    print("="*60 + "\n")


def main():
    """Main execution function."""
    # Parse arguments
    args = parse_arguments()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    logger.info("="*60)
    logger.info("Overton Researcher Tracker Started")
    logger.info("="*60)
    
    try:
        # Load researcher data
        logger.info(f"Loading researcher data from {args.input}")
        df = load_researchers(args.input)
        
        # Validate data
        if not validate_researchers(df):
            logger.error("Data validation failed")
            sys.exit(1)
        
        # Initialize API client
        logger.info("Initializing Overton API client")
        client = OvertonAPIClient(
            api_key=args.api_key,
            delay=args.delay,
            max_retries=args.retry
        )
        
        # Process researchers
        logger.info(f"Processing {len(df)} researchers...")
        results_df = process_researchers(df, client, args.institution)
        
        # Save results
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        results_df.to_csv(output_path, index=False)
        logger.info(f"Results saved to {output_path}")
        
        # Print summary
        print_summary(results_df)
        
        logger.info("Processing complete!")
        
    except KeyboardInterrupt:
        logger.warning("\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()