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

from data_processor import load_researchers, validate_researchers
from api_client import OvertonAPIClient
from metrics.registry import registry


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
        description='Query Overton API for Penn State researcher publications and policy documents.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract basic counts (backward compatible)
  %(prog)s --input data.xls --output results.csv --api-key YOUR_KEY \\
      --metrics publications_count documents_count
  
  # Extract country metrics
  %(prog)s --input data.xls --output results.csv --api-key YOUR_KEY \\
      --metrics citation_countries unique_country_count
  
  # Extract all available metrics
  %(prog)s --input data.xls --output results.csv --api-key YOUR_KEY
  
  # List available metrics
  %(prog)s --list-metrics
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        help='Path to Excel file containing researcher names'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Path for output CSV file'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
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
    
    parser.add_argument(
        '--metrics',
        type=str,
        nargs='+',
        default=None,
        help='Specific metrics to extract (default: all available). '
             'Use --list-metrics to see options.'
    )
    
    parser.add_argument(
        '--list-metrics',
        action='store_true',
        help='List all available metrics and exit'
    )
    
    return parser.parse_args()


def process_researchers(df: pd.DataFrame, client: OvertonAPIClient,
                       institution: str, selected_metrics=None):
    """
    Process all researchers and extract selected metrics.
    
    Args:
        df: DataFrame containing researcher data
        client: OvertonAPIClient instance
        institution: Institution name
        selected_metrics: List of metric names to extract (None = all)
        
    Returns:
        DataFrame with results
    """
    logger = logging.getLogger(__name__)
    
    # Get extractors for selected metrics
    extractors = registry.get_extractors(selected_metrics)
    
    if not extractors:
        logger.error("No valid extractors found!")
        return pd.DataFrame()
    
    # Log which metrics are being extracted
    metric_names = [e.metric_name for e in extractors]
    logger.info(f"Extracting metrics: {', '.join(metric_names)}")
    
    # Determine which API calls are needed
    need_pubs = any(e.requires_publications for e in extractors)
    need_docs = any(e.requires_documents for e in extractors)
    
    logger.info(f"API calls needed - Publications: {need_pubs}, Documents: {need_docs}")
    
    results = []
    
    # Progress bar
    with tqdm(total=len(df), desc="Processing researchers", unit="researcher") as pbar:
        for idx, row in df.iterrows():
            name = row['Name']
            pbar.set_description(f"Processing: {name[:30]}")
            
            # Make API calls only if needed
            pub_response = None
            doc_response = None
            error_msg = None
            
            if need_pubs:
                pub_result = client.query_publications(institution, name)
                pub_response = pub_result.get('full_response')
                if pub_result.get('error'):
                    error_msg = pub_result['error']
            
            if need_docs:
                doc_result = client.query_documents(institution, name)
                doc_response = doc_result.get('full_response')
                if doc_result.get('error') and not error_msg:
                    error_msg = doc_result['error']
            
            # Extract all metrics
            row_data = {'Name': name}
            
            for extractor in extractors:
                try:
                    value = extractor.extract(pub_response, doc_response, name)
                    
                    # Handle multi-column extractors
                    if isinstance(value, dict):
                        row_data.update(value)
                    else:
                        row_data[extractor.metric_name] = value
                        
                except Exception as e:
                    logger.error(f"Error extracting {extractor.metric_name} for {name}: {e}")
                    # Set to None for single metric, or set all columns to None for multi-column
                    col_names = extractor.get_column_names()
                    for col in col_names:
                        row_data[col] = None
            
            # Add status and metadata
            row_data['status'] = 'error' if error_msg else 'success'
            row_data['error'] = error_msg
            row_data['processed_at'] = datetime.now().isoformat()
            
            results.append(row_data)
            pbar.update(1)
    
    return pd.DataFrame(results)


def print_summary(results_df: pd.DataFrame):
    """Print summary statistics (flexible based on available metrics)."""
    logger = logging.getLogger(__name__)
    
    total = len(results_df)
    successful = len(results_df[results_df['status'] == 'success'])
    errors = len(results_df[results_df['status'] == 'error'])
    
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Total researchers processed: {total}")
    print(f"Successful queries: {successful} ({successful/total*100:.1f}%)")
    print(f"Failed queries: {errors} ({errors/total*100:.1f}%)")
    
    # Show metrics that were extracted
    numeric_cols = results_df.select_dtypes(include=['int64', 'float64']).columns
    metric_cols = [col for col in numeric_cols if col not in ['status']]
    
    if metric_cols:
        print(f"\nMetrics extracted:")
        for col in metric_cols:
            total_val = results_df[col].sum()
            avg_val = results_df[col].mean()
            print(f"  {col}: Total={total_val}, Average={avg_val:.1f}")
    
    # Show publications summary if available
    if 'publications_count' in results_df.columns:
        print(f"\nTop 5 researchers by publications:")
        top_pubs = results_df.nlargest(5, 'publications_count')[['Name', 'publications_count']]
        for idx, row in top_pubs.iterrows():
            print(f"  {row['Name']}: {row['publications_count']}")
    
    # Show documents summary if available
    if 'documents_count' in results_df.columns:
        print(f"\nTop 5 researchers by policy documents:")
        top_docs = results_df.nlargest(5, 'documents_count')[['Name', 'documents_count']]
        for idx, row in top_docs.iterrows():
            print(f"  {row['Name']}: {row['documents_count']}")
    
    # Show sample of extracted data
    print(f"\nSample of extracted metrics (first 3 researchers):")
    display_cols = ['Name'] + [col for col in results_df.columns if col not in ['status', 'error', 'processed_at']]
    print(results_df[display_cols].head(3).to_string(index=False))
    
    print("="*60 + "\n")


def main():
    """Main execution function."""
    # Parse arguments
    args = parse_arguments()
    
    # Initialize the registry with default extractors
    registry.initialize_default_extractors()
    
    # Handle --list-metrics
    if args.list_metrics:
        print("\n" + "="*60)
        print("AVAILABLE METRICS")
        print("="*60)
        
        metrics_info = registry.get_metrics_info()
        
        print(f"\n{'Metric Name':<30} {'Requires Pubs':<15} {'Requires Docs':<15}")
        print("-" * 60)
        
        for info in metrics_info:
            print(f"{info['name']:<30} {str(info['requires_publications']):<15} {str(info['requires_documents']):<15}")
        
        print(f"\nTotal metrics available: {len(metrics_info)}")
        print("\nUsage:")
        print("  # Extract specific metrics")
        print("  python main.py --input data.xls --output results.csv --api-key KEY \\")
        print("      --metrics publications_count citation_countries")
        print("\n  # Extract all metrics")
        print("  python main.py --input data.xls --output results.csv --api-key KEY")
        print("="*60 + "\n")
        sys.exit(0)
    
    # Validate required arguments when not listing metrics
    if not args.input or not args.output or not args.api_key:
        print("Error: --input, --output, and --api-key are required")
        print("Use --list-metrics to see available metrics")
        sys.exit(1)
    
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
        
        # Process researchers with selected metrics
        logger.info(f"Processing {len(df)} researchers...")
        results_df = process_researchers(
            df,
            client,
            args.institution,
            selected_metrics=args.metrics
        )
        
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