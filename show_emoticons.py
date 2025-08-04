#!/usr/bin/env python3
"""
Script to display all emoticons for a given Steam user.
Can fetch from database (if user is stored as villain) or directly from Steam API.

Usage:
    python3 show_emoticons.py <steam_id_or_url>
    python3 show_emoticons.py https://steamcommunity.com/id/username
    python3 show_emoticons.py https://steamcommunity.com/profiles/76561198000000000
    python3 show_emoticons.py 76561198000000000
"""

import sys
import asyncio
import argparse
import json
from typing import Optional, List, Dict

# Add src directory to path for imports
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import aiohttp
from src.database import PostgresDatabase
from src.steam_api import resolve_steam_url, get_steam_emoticons
from src.config import config


def display_emoticons(emoticons: List[Dict], steam_id: str, source: str = "") -> None:
    """
    Display emoticons in a formatted way.
    """
    if not emoticons:
        print(f"\n{'='*60}")
        print(f"No emoticons found for Steam ID: {steam_id}")
        print("This could mean:")
        print("  • Inventory is private")
        print("  • User has no emoticons")
        print("  • User profile doesn't exist")
        print(f"{'='*60}\n")
        return

    print(f"\n{'='*60}")
    print(f"Steam Emoticons for ID: {steam_id}")
    if source:
        print(f"Source: {source}")
    print(f"Found {len(emoticons)} unique emoticon(s)")
    print(f"{'='*60}\n")

    # Sort by game name
    emoticons.sort(key=lambda x: x.get('game', 'Unknown'))

    current_game = None
    total_quantity = 0
    
    for emoticon in emoticons:
        game = emoticon.get('game', 'Unknown')
        if game != current_game:
            current_game = game
            print(f"\n📮 Game: {current_game}")
            print("-" * 40)

        name = emoticon.get('name', 'Unknown')
        quantity = emoticon.get('quantity', 1)
        tradable = emoticon.get('tradable', 0)
        marketable = emoticon.get('marketable', 0)
        icon_url = emoticon.get('icon_url', '')
        
        total_quantity += quantity
        
        print(f"  • {name}")
        print(f"    Quantity: {quantity}")
        print(f"    Tradable: {'Yes' if tradable else 'No'}")
        print(f"    Marketable: {'Yes' if marketable else 'No'}")
        if icon_url:
            print(f"    Icon: {icon_url[:60]}...")
        print()
    
    print(f"{'='*60}")
    print(f"Total Emoticons: {total_quantity}")
    print(f"{'='*60}")


async def get_emoticons_from_database(steam_id: str) -> Optional[List[Dict]]:
    """
    Try to get emoticons from the database if the user is stored as a villain.
    """
    try:
        with PostgresDatabase() as db:
            villain = db.get_villain(steam_id)
            if villain and villain.get('emoticons'):
                print(f"Found user in database as villain")
                return villain['emoticons']
            else:
                print(f"User not found in database or no emoticons stored")
                return None
    except Exception as e:
        print(f"Error accessing database: {e}")
        return None


async def get_emoticons_from_steam(steam_id_or_url: str) -> Optional[List[Dict]]:
    """
    Fetch emoticons directly from Steam API.
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Resolve URL to Steam ID if needed
            if steam_id_or_url.startswith('http'):
                print(f"Resolving Steam URL: {steam_id_or_url}")
                steam_id = await resolve_steam_url(steam_id_or_url, session)
                print(f"Resolved to Steam ID: {steam_id}")
            else:
                steam_id = steam_id_or_url
            
            # Validate Steam ID format
            if not (steam_id.isdigit() and len(steam_id) == 17):
                print(f"Error: Invalid Steam ID format: {steam_id}")
                return None
            
            # Fetch emoticons
            print(f"Fetching emoticons directly from Steam API...")
            emoticons = await get_steam_emoticons(steam_id, session)
            return emoticons
            
    except Exception as e:
        print(f"Error fetching from Steam API: {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(
        description="Display Steam emoticons for a given user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 show_emoticons.py https://steamcommunity.com/id/username
  python3 show_emoticons.py https://steamcommunity.com/profiles/76561198000000000
  python3 show_emoticons.py 76561198000000000
  python3 show_emoticons.py username
  python3 show_emoticons.py --database-only 76561198000000000
  python3 show_emoticons.py --steam-only https://steamcommunity.com/id/username
        """
    )
    
    parser.add_argument(
        'steam_input',
        help='Steam ID (17 digits), Steam profile URL, or Steam username/alias'
    )
    
    parser.add_argument(
        '--database-only',
        action='store_true',
        help='Only check database, do not fetch from Steam API'
    )
    
    parser.add_argument(
        '--steam-only',
        action='store_true',
        help='Only fetch from Steam API, skip database check'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output raw JSON data instead of formatted display'
    )
    
    args = parser.parse_args()
    
    if args.database_only and args.steam_only:
        print("Error: Cannot use both --database-only and --steam-only")
        sys.exit(1)
    
    steam_input = args.steam_input
    
    # Convert plain username to Steam profile URL if needed
    if not steam_input.startswith('http') and not (steam_input.isdigit() and len(steam_input) == 17):
        # Assume it's a username/alias, convert to Steam profile URL
        steam_input = f"https://steamcommunity.com/id/{steam_input}"
        print(f"Converting username to Steam URL: {steam_input}")
    
    emoticons = None
    source = ""
    
    # Try database first (unless steam-only is specified)
    if not args.steam_only:
        # If input is URL, we need to resolve it to get Steam ID for database lookup
        if steam_input.startswith('http'):
            try:
                async with aiohttp.ClientSession() as session:
                    resolved_steam_id = await resolve_steam_url(steam_input, session)
                    emoticons = await get_emoticons_from_database(resolved_steam_id)
                    if emoticons:
                        source = "Database"
                        steam_input = resolved_steam_id  # Use resolved ID for display
            except Exception as e:
                print(f"Error resolving URL for database lookup: {e}")
        else:
            emoticons = await get_emoticons_from_database(steam_input)
            if emoticons:
                source = "Database"
    
    # Try Steam API if database didn't work (unless database-only is specified)
    if not emoticons and not args.database_only:
        emoticons = await get_emoticons_from_steam(steam_input)
        if emoticons:
            source = "Steam API"
            # Update steam_input to be the resolved Steam ID if it was a URL
            if steam_input.startswith('http'):
                try:
                    async with aiohttp.ClientSession() as session:
                        steam_input = await resolve_steam_url(steam_input, session)
                except:
                    pass  # Keep original input if resolution fails
    
    # Display results
    if args.json:
        if emoticons:
            print(json.dumps(emoticons, indent=2))
        else:
            print("null")
    else:
        display_emoticons(emoticons or [], steam_input, source)
    
    # Exit with appropriate code
    sys.exit(0 if emoticons else 1)


if __name__ == "__main__":
    asyncio.run(main())