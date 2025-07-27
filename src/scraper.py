"""Web scraping and comment analysis functions"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import logging
import time
from dateutil import parser
from .config import config, get_compiled_patterns
from .steam_api import resolve_steam_url
from .retry_utils import retry_with_exponential_backoff

@retry_with_exponential_backoff()
async def scrape_profile_comments(steamid64, session):
    """
    Scrapes all comments from a Steam profile using Steam's comment API

    Args:
        steamid64: The Steam ID to scrape
        session: aiohttp session (required)

    Returns:
        list: List of comment dictionaries
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    }

    try:
        comments = []
        start = 0
        count = 50  # Steam's typical page size
        
        while True:
            # Use Steam's comment API endpoint
            api_url = f"https://steamcommunity.com/comment/Profile/render/{steamid64}/-1/"
            
            # Prepare form data for POST request
            form_data = {
                'start': str(start),
                'count': str(count),
                'feature2': '-1'
            }
            
            try:
                async with session.post(api_url, headers=headers, data=form_data) as response:
                    if response.status != 200:
                        logging.warning(f"Steam profile API request failed with status {response.status}")
                        break
                        
                    json_data = await response.json()
            except aiohttp.ClientConnectorError as e:
                logging.error(f"Failed to connect to Steam profile API: {e}")
                raise aiohttp.ClientConnectorError(f"Failed to connect to Steam profile: {e}")
            except aiohttp.ClientTimeout as e:
                logging.error(f"Steam profile request timed out: {e}")
                raise aiohttp.ClientTimeout(f"Steam profile request timed out: {e}")
            except aiohttp.ClientError as e:
                logging.error(f"Network error accessing Steam profile: {e}")
                raise aiohttp.ClientError(f"Network error accessing Steam profile: {e}")
                
            # Check if we got comments HTML
            if 'comments_html' not in json_data or not json_data['comments_html']:
                break
                
            # Parse the HTML from the API response
            soup = BeautifulSoup(json_data['comments_html'], 'lxml')
            
            # Try multiple selectors for comment containers
            comment_divs = []
            for selector in [
                'div.commentthread_comment',
                'div[class*="comment"]',
                '.comment',
                '[id*="comment"]'
            ]:
                comment_divs = soup.select(selector)
                if comment_divs:
                    break
            
            if not comment_divs:
                break
                
            # Extract comments from this page
            page_comments = []
            for comment_div in comment_divs:
                comment_data = extract_comment_data(comment_div)
                if comment_data:
                    page_comments.append(comment_data)
            
            comments.extend(page_comments)
            
            # Check if we got fewer comments than requested (end of comments)
            if len(page_comments) < count:
                break
                    
                # Move to next page
                start += count

        return comments

    except Exception as e:
        logging.error(f"Error scraping profile {steamid64}: {e}")
        return []

def extract_comment_data(comment_element):
    """
    Extracts data from a comment HTML element with robust selectors
    """
    try:
        # Extract commenter info with multiple fallback selectors
        author_link = None
        for selector in [
            'a.commentthread_author_link',
            'a[class*="author"]',
            '.commentthread_comment_author a',
            '.commentthread_comment_content a[href*="/id/"]',
            '.commentthread_comment_content a[href*="/profiles/"]'
        ]:
            author_link = comment_element.select_one(selector)
            if author_link:
                break
        
        if not author_link:
            logging.warning("Could not find author link in comment")
            return None
            
        commenter_url = author_link.get('href', '')
        commenter_name = author_link.get_text(strip=True)

        # Extract comment text with multiple fallback selectors
        comment_text_element = None
        for selector in [
            '.commentthread_comment_text',
            '.commentthread_comment_content .comment_text',
            '.commentthread_comment_content div[class*="text"]',
            '.comment_content'
        ]:
            comment_text_element = comment_element.select_one(selector)
            if comment_text_element:
                break
        
        if not comment_text_element:
            logging.warning("Could not find comment text in comment")
            return None
            
        comment_text = comment_text_element.get_text(strip=True)

        # Extract date with multiple fallback selectors
        timestamp_element = None
        for selector in [
            '.commentthread_comment_timestamp',
            '.timestamp',
            'span[class*="timestamp"]',
            '.commentthread_comment_content .date',
            'time'
        ]:
            timestamp_element = comment_element.select_one(selector)
            if timestamp_element:
                break
        
        comment_date = None
        if timestamp_element:
            # Try different attributes for timestamp
            timestamp_text = (
                timestamp_element.get('title') or 
                timestamp_element.get('datetime') or 
                timestamp_element.get_text(strip=True)
            )
            comment_date = parse_steam_date(timestamp_text)

        return {
            'commenter_url': commenter_url,
            'commenter_name': commenter_name,
            'comment_text': comment_text,
            'comment_date': comment_date
        }
    except Exception as e:
        logging.warning(f"Error extracting comment data: {e}")
        return None

def parse_steam_date(date_str):
    """
    Parses Steam date strings to datetime objects
    
    Handles various Steam timestamp formats like:
    - "2 hours ago"
    - "yesterday" 
    - "Jan 15"
    - "Jan 15, 2023"
    - Standard date formats
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    date_str = date_str.strip().lower()
    
    try:
        from datetime import datetime, timedelta
        import calendar
        
        now = datetime.now()
        
        # Handle relative time formats
        if "ago" in date_str:
            number_match = re.search(r'(\d+)', date_str)
            if number_match:
                number = int(number_match.group(1))
                if "minute" in date_str or "min" in date_str:
                    return now - timedelta(minutes=number)
                elif "hour" in date_str:
                    return now - timedelta(hours=number)
                elif "day" in date_str:
                    return now - timedelta(days=number)
                elif "week" in date_str:
                    return now - timedelta(weeks=number)
                elif "month" in date_str:
                    return now - timedelta(days=number * 30)  # Approximate
                elif "year" in date_str:
                    return now - timedelta(days=number * 365)  # Approximate
        
        # Handle "yesterday"
        if date_str == "yesterday":
            return now - timedelta(days=1)
        
        # Handle "today"
        if date_str == "today":
            return now
        
        # Handle Steam format: "july 26, 2025 @ 1:59:22 pm pdt"
        steam_match = re.match(r'(\w+)\s+(\d+),\s*(\d{4})\s*@\s*(\d+):(\d+):(\d+)\s*(am|pm)\s*(pdt|pst|edt|est|cdt|cst|mdt|mst)', date_str)
        if steam_match:
            month_name, day, year, hour, minute, second, ampm, tz = steam_match.groups()
            
            # Convert month name to number
            month_names = {name.lower(): num for num, name in enumerate(calendar.month_name) if name}
            if month_name in month_names:
                month = month_names[month_name]
                day = int(day)
                year = int(year)
                hour = int(hour)
                minute = int(minute)
                second = int(second)
                
                # Convert 12-hour to 24-hour format
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                return datetime(year, month, day, hour, minute, second)

        # Handle month abbreviations (Jan 15, Feb 3, etc.)
        month_match = re.match(r'(\w{3})\s+(\d+)(?:,\s*(\d{4}))?', date_str)
        if month_match:
            month_abbr, day, year = month_match.groups()
            month_names = {name.lower(): num for num, name in enumerate(calendar.month_abbr) if name}
            
            if month_abbr in month_names:
                month = month_names[month_abbr]
                day = int(day)
                year = int(year) if year else now.year
                
                # If the date is in the future for current year, assume previous year
                test_date = datetime(year, month, day)
                if year == now.year and test_date > now:
                    year -= 1
                
                return datetime(year, month, day)
        
        # Fall back to dateutil parser for standard formats
        return parser.parse(date_str)
        
    except Exception as e:
        logging.warning(f"Failed to parse date '{date_str}': {e}")
        return None


def check_for_hate_speech(comment_text):
    """
    Checks if comment contains hate speech terms using pre-compiled patterns

    Args:
        comment_text: The comment text to check

    Returns:
        bool: True if hate speech detected
    """
    comment_lower = comment_text.lower()

    # Check simple string terms
    for term in config.hate_terms:
        if term.lower() in comment_lower:
            return True

    # Check pre-compiled regex patterns
    for compiled_pattern in get_compiled_patterns():
        if compiled_pattern.search(comment_text):
            return True

    return False