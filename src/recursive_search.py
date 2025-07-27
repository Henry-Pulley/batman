"""Recursive search logic for finding hate speech commenters"""

import asyncio
import aiohttp
import logging
from asyncio import Queue
from .config import config
from .steam_api import resolve_steam_url
from .scraper import scrape_profile_comments, check_for_hate_speech
from .database import PostgresDatabase
from .report import generate_report
from .rate_limiter import SimpleRateLimiter

async def recursive_profile_search(initial_url):
    """
    Main recursive search function with async operations

    Args:
        initial_url: Starting Steam profile URL
    """
    # Initialize
    with PostgresDatabase() as db:
        queue = Queue()
        visited_ids = set()
        queued_ids = set()
        rate_limiter = SimpleRateLimiter()

        # Use default SSL context for secure connections
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            # Resolve initial URL
            initial_steamid = await resolve_steam_url(initial_url, session)
            await queue.put({
                'steamid': initial_steamid,
                'path': initial_steamid
            })
            queued_ids.add(initial_steamid)

            # Create worker tasks
            workers = [
                asyncio.create_task(
                    process_profile_worker(queue, visited_ids, queued_ids, db, session, rate_limiter)
                ) for _ in range(config.max_concurrent_requests)
            ]

            # Wait for the queue to be fully processed
            await queue.join()

            # Cancel the worker tasks, as they are now idle in their while True loop
            for worker in workers:
                worker.cancel()

            # Wait for workers to finish cancelling
            await asyncio.gather(*workers, return_exceptions=True)

        # Generate final report
        generate_report(db)


async def process_profile_worker(queue, visited_ids, queued_ids, db, session, rate_limiter):
    """
    Worker coroutine to process profiles from the queue
    """
    while True:
        try:
            # Wait for an item from the queue with timeout
            current = await asyncio.wait_for(queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            # No more items in queue, exit worker
            break

        current_steamid = current['steamid']
        current_path = current['path']

        # Skip if already visited
        if current_steamid in visited_ids:
            queue.task_done()
            continue

        visited_ids.add(current_steamid)
        logging.info(f"Processing profile: {current_steamid}")

        # Use rate limiter for this request
        async with rate_limiter:
            # Scrape comments
            comments = await scrape_profile_comments(current_steamid, session)

        # Process each comment
        for comment in comments:
            if check_for_hate_speech(comment['comment_text']):
                # Get commenter's SteamID
                try:
                    async with rate_limiter:
                        commenter_steamid = await resolve_steam_url(comment['commenter_url'], session)
                except Exception as e:
                    logging.warning(f"Could not resolve commenter URL: {e}")
                    continue

                # Prepare data for database
                flagged_data = {
                    'commenter_steamid': commenter_steamid,
                    'commenter_alias': comment['commenter_name'],
                    'profile_steamid': current_steamid,
                    'comment_text': comment['comment_text'],
                    'comment_date': comment['comment_date'],
                    'friend_path': current_path
                }

                # Store in database
                if db.insert_flagged_comment(flagged_data):
                    logging.info(f"Flagged comment from {commenter_steamid}")

                    # Add to villains table
                    db.insert_villain(commenter_steamid, comment['commenter_name'])
                    logging.info(f"Added/updated villain: {commenter_steamid}")

                    # Add commenter to queue if not visited or already queued
                    if commenter_steamid not in visited_ids and commenter_steamid not in queued_ids:
                        new_path = f"{current_path} -> {commenter_steamid}"
                        await queue.put({
                            'steamid': commenter_steamid,
                            'path': new_path
                        })
                        queued_ids.add(commenter_steamid)

        queue.task_done()