#!/usr/bin/env python3
"""
Bulk Avatar Update Script

This script fetches and updates avatar data for all villains in the database
that are missing profile pictures. It uses the Steam API to fetch avatar URLs
and stores them in the database.

Usage:
    python3 update_avatars.py [--dry-run] [--limit N]
    
Arguments:
    --dry-run: Show what would be updated without making changes
    --limit N: Only process N profiles (for testing)
"""

import asyncio
import aiohttp
import argparse
import logging
import time
from typing import List, Tuple
from src.steam_api import get_player_avatars, serialize_avatar_data
from src.database import PostgresDatabase
from src.config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AvatarUpdater:
    def __init__(self, dry_run: bool = False, limit: int = None):
        self.dry_run = dry_run
        self.limit = limit
        self.stats = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def get_profiles_missing_avatars(self) -> List[Tuple[str, str]]:
        """Get list of (steam_id, aliases) for profiles missing avatar data"""
        with PostgresDatabase() as db:
            query = """
                SELECT steam_id, aliases 
                FROM villains 
                WHERE profile_pictures IS NULL 
                ORDER BY steam_id
            """
            if self.limit:
                query += f" LIMIT {self.limit}"
            
            db.cursor.execute(query)
            results = db.cursor.fetchall()
            
            return [(row['steam_id'], row['aliases']) for row in results]
    
    async def fetch_avatar_data(self, steam_id: str, session: aiohttp.ClientSession) -> dict:
        """Fetch avatar data for a single Steam ID"""
        try:
            avatar_data = await get_player_avatars(steam_id, session)
            return avatar_data
        except Exception as e:
            logger.error(f"Failed to fetch avatar for {steam_id}: {e}")
            return None
    
    def update_profile_avatar(self, steam_id: str, avatar_data: dict) -> bool:
        """Update a profile's avatar data in the database"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would update avatar for {steam_id}")
            return True
        
        try:
            avatar_json = serialize_avatar_data(avatar_data)
            
            with PostgresDatabase() as db:
                db.cursor.execute(
                    """
                    UPDATE villains 
                    SET profile_pictures = %s, last_avatar_update = CURRENT_TIMESTAMP 
                    WHERE steam_id = %s
                    """,
                    (avatar_json, steam_id)
                )
                db.conn.commit()
                
                if db.cursor.rowcount > 0:
                    logger.info(f"✓ Updated avatar for {steam_id}")
                    return True
                else:
                    logger.warning(f"✗ No rows updated for {steam_id}")
                    return False
        except Exception as e:
            logger.error(f"✗ Database error updating {steam_id}: {e}")
            return False
    
    async def process_batch(self, profiles: List[Tuple[str, str]], session: aiohttp.ClientSession) -> None:
        """Process a batch of profiles"""
        semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        
        async def process_single(steam_id: str, aliases: str):
            async with semaphore:
                self.stats['processed'] += 1
                
                logger.info(f"Processing {self.stats['processed']}: {steam_id} ({aliases})")
                
                # Fetch avatar data
                avatar_data = await self.fetch_avatar_data(steam_id, session)
                
                if avatar_data:
                    # Check if avatar URL is valid (not default Steam avatar)
                    avatar_url = avatar_data.get('avatar', '')
                    if avatar_url and 'fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb' not in avatar_url:
                        # Update database
                        if self.update_profile_avatar(steam_id, avatar_data):
                            self.stats['success'] += 1
                        else:
                            self.stats['failed'] += 1
                    else:
                        logger.info(f"↺ Skipping {steam_id} (default avatar)")
                        self.stats['skipped'] += 1
                else:
                    logger.warning(f"✗ No avatar data for {steam_id}")
                    self.stats['failed'] += 1
                
                # Rate limiting delay
                await asyncio.sleep(config.request_delay)
        
        # Process all profiles concurrently
        tasks = [process_single(steam_id, aliases) for steam_id, aliases in profiles]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run(self) -> None:
        """Main execution function"""
        logger.info("Starting bulk avatar update...")
        
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No changes will be made")
        
        # Get profiles missing avatars
        profiles = self.get_profiles_missing_avatars()
        
        if not profiles:
            logger.info("✓ All profiles already have avatar data!")
            return
        
        logger.info(f"Found {len(profiles)} profiles missing avatar data")
        
        if self.limit:
            logger.info(f"Processing limited to {self.limit} profiles")
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(
            limit=config.connection_pool_size,
            limit_per_host=config.max_concurrent_requests,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=config.keepalive_timeout
        )
        
        start_time = time.time()
        
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        ) as session:
            await self.process_batch(profiles, session)
        
        # Print summary
        elapsed = time.time() - start_time
        logger.info("\n" + "="*50)
        logger.info("BULK AVATAR UPDATE SUMMARY")
        logger.info("="*50)
        logger.info(f"Total processed: {self.stats['processed']}")
        logger.info(f"Successfully updated: {self.stats['success']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Skipped (default avatars): {self.stats['skipped']}")
        logger.info(f"Time elapsed: {elapsed:.2f} seconds")
        
        if self.stats['processed'] > 0:
            rate = self.stats['processed'] / elapsed
            logger.info(f"Processing rate: {rate:.2f} profiles/second")
        
        if not self.dry_run and self.stats['success'] > 0:
            logger.info(f"✓ Database updated with {self.stats['success']} new avatars")


def main():
    parser = argparse.ArgumentParser(description='Bulk update avatar data for villains')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be updated without making changes')
    parser.add_argument('--limit', type=int, metavar='N',
                       help='Only process N profiles (for testing)')
    
    args = parser.parse_args()
    
    # Check if Steam API key is configured
    if not config.steam_api_key:
        logger.error("❌ Steam API key not configured. Please set STEAM_API_KEY environment variable.")
        return
    
    # Run the updater
    updater = AvatarUpdater(dry_run=args.dry_run, limit=args.limit)
    
    try:
        asyncio.run(updater.run())
    except KeyboardInterrupt:
        logger.info("\n❌ Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()