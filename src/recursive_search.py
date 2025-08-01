"""Recursive search logic for finding hate speech commenters"""

import asyncio
import aiohttp
import logging
import time
from asyncio import Queue
from .config import config
from .steam_api import resolve_steam_url
from .scraper import scrape_profile_comments, check_for_hate_speech, scrape_friends_list
from .database import PostgresDatabase
from .report import generate_report
from .rate_limiter import TokenBucketRateLimiter

def should_shutdown(shared_state):
    """
    Check if the system should shutdown based on configured limits
    
    Args:
        shared_state (dict): Shared state containing counters and timing info
        
    Returns:
        bool: True if shutdown should be initiated
    """
    # Check profile limit
    if config.max_profiles_to_process > 0:
        if shared_state['processed_count'] >= config.max_profiles_to_process:
            shared_state['shutdown_requested'] = True
            shared_state['shutdown_reason'] = 'profile_limit'
            return True
    
    # Check time limit
    if config.max_processing_time_minutes > 0:
        elapsed_minutes = (time.time() - shared_state['start_time']) / 60
        if elapsed_minutes >= config.max_processing_time_minutes:
            shared_state['shutdown_requested'] = True
            shared_state['shutdown_reason'] = 'time_limit'
            return True
    
    return False

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
        
        # Initialize tracking variables
        start_time = time.time()
        processed_count = 0
        shutdown_reason = None
        
        # Shared state for workers
        shared_state = {
            'processed_count': 0,
            'shutdown_requested': False,
            'shutdown_reason': None,
            'start_time': start_time
        }
        
        rate_limiter = TokenBucketRateLimiter(
            rate=int(1.0/config.request_delay),  # Convert delay to rate (requests per second)
            capacity=config.max_concurrent_requests
        )

        # Use default SSL context for secure connections
        connector = aiohttp.TCPConnector(
            limit=config.connection_pool_size,  # Total connections
            limit_per_host=50,  # Per-host limit
            ttl_dns_cache=300,  # DNS cache for 5 minutes
            enable_cleanup_closed=True,
            keepalive_timeout=config.keepalive_timeout
        )

        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        
        async with aiohttp.ClientSession(
            connector=connector, 
            timeout=timeout, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as session:
            # Resolve initial URL
            initial_steamid = await resolve_steam_url(initial_url, session)
            await queue.put({
                'steamid': initial_steamid,
                'path': initial_steamid,
                'depth': 0
            })
            queued_ids.add(initial_steamid)

            # Create worker tasks
            workers = [
                asyncio.create_task(
                    process_profile_worker(queue, visited_ids, queued_ids, db, session, rate_limiter, shared_state)
                ) for _ in range(config.max_concurrent_requests)
            ]

            # Wait for the queue to be fully processed or shutdown requested
            while not queue.empty() or any(not w.done() for w in workers):
                await asyncio.sleep(0.1)
                if shared_state['shutdown_requested']:
                    break

            # Cancel the worker tasks
            for worker in workers:
                worker.cancel()

            # Wait for workers to finish cancelling
            await asyncio.gather(*workers, return_exceptions=True)

            # Handle graceful shutdown
            processed_count = shared_state['processed_count']
            shutdown_reason = shared_state['shutdown_reason']
            
            if shutdown_reason:
                # Save unprocessed profiles
                unprocessed_profiles = []
                while not queue.empty():
                    try:
                        item = queue.get_nowait()
                        unprocessed_profiles.append((
                            item['steamid'], 
                            item['path'], 
                            item.get('depth', 0)
                        ))
                        queue.task_done()
                    except asyncio.QueueEmpty:
                        break
                
                # Save to database
                if unprocessed_profiles:
                    saved_count = db.save_unprocessed_profiles(unprocessed_profiles, shutdown_reason)
                    logging.info(f"Saved {saved_count} unprocessed profiles to database")
                
                # Log shutdown information
                elapsed_time = time.time() - start_time
                logging.info(f"System shutdown due to {shutdown_reason}")
                logging.info(f"Processed {processed_count} profiles in {elapsed_time:.2f} seconds")
                logging.info(f"Unprocessed profiles saved: {len(unprocessed_profiles)}")
            else:
                logging.info(f"Search completed normally. Processed {processed_count} profiles")

        # Generate final report
        generate_report(db)


# Update src/recursive_search.py - process_profile_worker function
# Replace the existing function with this optimized version:

async def process_profile_worker(queue, visited_ids, queued_ids, db, session, rate_limiter, shared_state):
    """
    Worker coroutine to process profiles from the queue with batch processing
    """
    while True:
        # Check if shutdown was requested
        if shared_state['shutdown_requested']:
            break
            
        try:
            # Wait for an item from the queue with timeout
            current = await asyncio.wait_for(queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            # No more items in queue, exit worker
            break

        current_steamid = current['steamid']
        current_path = current['path']
        current_depth = current.get('depth', 0)

        # Skip if already visited
        if current_steamid in visited_ids:
            queue.task_done()
            continue

        # Check limits before processing
        if should_shutdown(shared_state):
            # Put the item back and exit
            await queue.put(current)
            break

        visited_ids.add(current_steamid)
        shared_state['processed_count'] += 1
        
        logging.info(f"Processing profile {shared_state['processed_count']}: {current_steamid}")

        # Use rate limiter for this request
        async with rate_limiter:
            # Scrape comments
            comments = await scrape_profile_comments(current_steamid, session)

        # DEBUG: Log comment scraping results
        logging.info(f"Found {len(comments)} comments on profile {current_steamid}")
        for i, comment in enumerate(comments[:3]):  # Show first 3 comments
            comment_text = comment.get('comment_text', '')
            logging.info(f"  Comment {i+1}: \"{comment_text[:100]}{'...' if len(comment_text) > 100 else ''}\"")

        # OPTIMIZED: Collect flagged comments for batch processing
        flagged_comments_batch = []
        villains_to_add = []
        new_profiles_to_queue = []

        # Process each comment
        for comment in comments:
            if check_for_hate_speech(comment['comment_text']):
                logging.info(f"  HATE SPEECH DETECTED: \"{comment['comment_text'][:100]}{'...' if len(comment['comment_text']) > 100 else ''}\"")
                logging.info(f"  Commenter: {comment.get('commenter_name', 'Unknown')} ({comment.get('commenter_url', 'No URL')})")
                # Get commenter's SteamID
                try:
                    async with rate_limiter:
                        commenter_steamid = await resolve_steam_url(comment['commenter_url'], session)
                except Exception as e:
                    logging.warning(f"Could not resolve commenter URL: {e}")
                    continue

                # Prepare data for batch insert
                flagged_data = {
                    'commenter_steamid': commenter_steamid,
                    'commenter_alias': comment['commenter_name'],
                    'profile_steamid': current_steamid,
                    'comment_text': comment['comment_text'],
                    'comment_date': comment['comment_date'],
                    'friend_path': current_path
                }
                
                flagged_comments_batch.append(flagged_data)
                villains_to_add.append((commenter_steamid, comment['commenter_name']))

                # Prepare for queueing (but don't queue yet)
                if commenter_steamid not in visited_ids and commenter_steamid not in queued_ids:
                    new_profiles_to_queue.append({
                        'steamid': commenter_steamid,
                        'path': f"{current_path} -> {commenter_steamid}",
                        'depth': current_depth + 1
                    })

        # BATCH INSERT: Insert all flagged comments at once
        if flagged_comments_batch:
            inserted_count = db.insert_flagged_comments_batch(flagged_comments_batch)
            logging.info(f"Batch inserted {inserted_count} flagged comments from profile {current_steamid}")
            
            # Add villains
            for steamid, alias in villains_to_add:
                db.insert_villain(steamid, alias)
            
            # Queue new profiles only after successful insert
            for profile_data in new_profiles_to_queue:
                await queue.put(profile_data)
                queued_ids.add(profile_data['steamid'])

        # Scrape friends list and add them to the queue
        async with rate_limiter:
            friends = await scrape_friends_list(current_steamid, session)
        
        if friends:
            logging.info(f"Found {len(friends)} friends for profile {current_steamid}")
            for friend_steamid in friends:
                # Only queue friends that haven't been visited or queued
                if friend_steamid not in visited_ids and friend_steamid not in queued_ids:
                    await queue.put({
                        'steamid': friend_steamid,
                        'path': f"{current_path} -> {friend_steamid}",
                        'depth': current_depth + 1
                    })
                    queued_ids.add(friend_steamid)

        queue.task_done()