#!/usr/bin/env python3
"""
Steam Comment Analyzer
Main entry point for the application
"""

import sys
import argparse
import asyncio
import logging
from aiohttp import ClientError, ClientConnectorError
import psycopg2
from dotenv import load_dotenv
from src.config import config, compile_hate_patterns
from src.recursive_search import recursive_profile_search
from src.validators import SafetyValidator

# Load environment variables from .env file
load_dotenv()

# Initialize safety validator
validator = SafetyValidator()

def validate_url(url):
    """Validate Steam profile URL using SafetyValidator."""
    is_valid, error_message = validator.validate_url(url)
    if not is_valid and error_message:
        print(f"Validation error for {url}: {error_message}")
    return is_valid

async def process_urls(valid_urls):
    """Process multiple URLs concurrently"""
    tasks = []
    for i, url in enumerate(valid_urls, 1):
        print(f"\n[{i}/{len(valid_urls)}] Processing: {url}")
        task = asyncio.create_task(recursive_profile_search(url))
        tasks.append(task)
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks)

def parse_arguments():
    """Parse command line arguments using argparse"""
    parser = argparse.ArgumentParser(
        description="Steam Comment Analyzer - Analyze Steam profiles for hate speech content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use URLs from config.py
  %(prog)s https://steamcommunity.com/id/user # Analyze single profile
  %(prog)s --url profile1 --url profile2      # Analyze multiple profiles
        """
    )
    
    parser.add_argument(
        'url',
        nargs='?',
        help='Steam profile URL to analyze (overrides config URLs)'
    )
    
    parser.add_argument(
        '--url', '-u',
        action='append',
        dest='urls',
        help='Steam profile URL to analyze (can be used multiple times)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Steam Comment Analyzer 1.0'
    )
    
    return parser.parse_args()

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Configure logging
    logging.basicConfig(
        level=config.log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.log_file),
            logging.StreamHandler()
        ]
    )
    
    # Initialize compiled regex patterns for hate speech detection
    compile_hate_patterns()
    logging.info("Compiled regex patterns for hate speech detection")

    # Check API key
    if config.steam_api_key == "YOUR_STEAM_API_KEY_HERE":
        print("Error: Please set your Steam API key in config.py")
        print("You can get an API key from: https://steamcommunity.com/dev/apikey")
        sys.exit(1)

    # Determine URLs to analyze
    urls = []
    
    if args.urls:
        # Multiple URLs provided via --url flag
        urls = args.urls
    elif args.url:
        # Single URL provided as positional argument
        urls = [args.url]
    else:
        # No arguments - use URLs from config
        urls = config.target_urls
        if not urls:
            print("Error: No URLs specified in config.target_urls")
            print("Please add Steam profile URLs to the TARGET_URLS list in config.py")
            print("Example:")
            print('  TARGET_URLS = [')
            print('      "https://steamcommunity.com/id/username",')
            print('      "https://steamcommunity.com/profiles/76561198000000000",')
            print('  ]')
            print("\nOr use command line arguments:")
            print("  python main.py https://steamcommunity.com/id/username")
            print("  python main.py --url profile1 --url profile2")
            sys.exit(1)

    # Validate URLs
    valid_urls = []
    for url in urls:
        if validate_url(url):
            valid_urls.append(url)
        else:
            print(f"Warning: Skipping invalid URL: {url}")

    if not valid_urls:
        print("Error: No valid Steam profile URLs found")
        print("URLs must be in the format:")
        print("  https://steamcommunity.com/id/username")
        print("  https://steamcommunity.com/profiles/steamid64")
        sys.exit(1)

    try:
        print(f"\nStarting analysis of {len(valid_urls)} profile(s)")
        print("This may take a while depending on the number of profiles to check...")
        print("")
        
        # Process each URL
        asyncio.run(process_urls(valid_urls))
        
        print("\nAnalysis complete!")
        
    except KeyboardInterrupt:
        print("\n\nAnalysis interrupted by user")
        sys.exit(0)
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection failed: {e}")
        print(f"\nDatabase connection failed: {e}")
        print("Please check your PostgreSQL server is running and credentials are correct")
        sys.exit(1)
    except psycopg2.DatabaseError as e:
        logging.error(f"Database error: {e}")
        print(f"\nDatabase error: {e}")
        print("Please check your PostgreSQL configuration in config.py")
        sys.exit(1)
    except psycopg2.Error as e:
        logging.error(f"PostgreSQL error: {e}")
        print(f"\nPostgreSQL error: {e}")
        print("Please check your database setup and configuration")
        sys.exit(1)
    except ClientConnectorError as e:
        logging.error(f"Connection failed: {e}")
        print(f"\nFailed to connect to Steam servers: {e}")
        print("Please check your internet connection and try again")
        sys.exit(1)
    except ClientError as e:
        logging.error(f"Network error: {e}")
        print(f"\nNetwork error: {e}")
        print("Please check your internet connection and try again")
        sys.exit(1)
    except asyncio.TimeoutError:
        logging.error("Operation timed out")
        print("\nOperation timed out. The analysis took too long to complete.")
        print("Consider reducing the search depth or checking fewer profiles")
        sys.exit(1)
    except PermissionError as e:
        logging.error(f"Permission error: {e}")
        print(f"\nPermission error: {e}")
        print("Please check file permissions and try again")
        sys.exit(1)
    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
        print(f"\nFile not found: {e}")
        print("Please check that all required configuration files exist")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        print(f"\nConfiguration error: {e}")
        print("Please check your configuration settings")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        print(f"\nAn unexpected error occurred: {e}")
        print("Please check the log file for more details")
        sys.exit(1)

if __name__ == "__main__":
    main()