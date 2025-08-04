"""Steam API integration and profile resolution functions"""

import aiohttp
import time
import json
import logging
from typing import Optional, List, Dict
from .config import config
from .retry_utils import retry_with_exponential_backoff

# Simple cache for resolved Steam IDs
_steam_id_cache = {}
_cache_ttl = 3600  # 1 hour

# Avatar cache for profile pictures
_avatar_cache = {}
_avatar_cache_ttl = 7200  # 2 hours

async def resolve_steam_url(url, session):
    """
    Resolves a Steam profile URL to a SteamID64 with caching
    """
    # Check cache first
    cache_key = url
    if cache_key in _steam_id_cache:
        cached_id, timestamp = _steam_id_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return cached_id
        
    # Extract unique identifier from URL
    if "/id/" in url:
        identifier = url.split("/id/")[1].strip("/")
    elif "/profiles/" in url:
        identifier = url.split("/profiles/")[1].strip("/")
    else:
        raise ValueError("Invalid Steam profile URL")
    
    # Determine if identifier is alias or SteamID64
    if identifier.isdigit() and len(identifier) == 17:
        # SteamID64 is a 17-digit number
        result = identifier
    else:
        # Assume it's an alias
        result = await resolve_vanity_url(identifier, session)

    _steam_id_cache[cache_key] = (result, time.time())
    return result

@retry_with_exponential_backoff()
async def resolve_vanity_url(vanity_name, session):
    """
    Resolves vanity URL to SteamID64 using Steam API
    """
    endpoint = f"{config.steam_api_base}/ISteamUser/ResolveVanityURL/v0001/"
    params = {
        "key": config.steam_api_key,
        "vanityurl": vanity_name
    }

    # Debug logging
    import logging
    logging.info(f"Making request to {endpoint} with params: {{'key': '{'*' * len(params['key']) if params['key'] else 'EMPTY'}', 'vanityurl': '{params['vanityurl']}'}}")
    
    try:
        async with session.get(endpoint, params=params) as response:
            if response.status != 200:
                response_text = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Steam API returned status {response.status}. Response: {response_text}"
                )
            data = await response.json()
    except aiohttp.ClientConnectorError as e:
        raise aiohttp.ClientConnectorError(f"Failed to connect to Steam API: {e}")
    except aiohttp.ClientTimeout as e:
        raise aiohttp.ClientTimeout(f"Steam API request timed out: {e}")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"Network error contacting Steam API: {e}")

    if data["response"]["success"] == 1:
        return data["response"]["steamid"]
    else:
        raise ValueError(f"Could not resolve vanity URL: {vanity_name}")

@retry_with_exponential_backoff()
async def get_player_summary(steamid64, session):
    """
    Fetches player data from Steam API
    """
    endpoint = f"{config.steam_api_base}/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        "key": config.steam_api_key,
        "steamids": steamid64
    }

    # Debug logging
    import logging
    logging.info(f"Making request to {endpoint} with params: {{'key': '{'*' * len(params['key']) if params['key'] else 'EMPTY'}', 'steamids': '{params['steamids']}'}}")
    
    try:
        async with session.get(endpoint, params=params) as response:
            if response.status != 200:
                response_text = await response.text()
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Steam API returned status {response.status}. Response: {response_text}"
                )
            data = await response.json()
    except aiohttp.ClientConnectorError as e:
        raise aiohttp.ClientConnectorError(f"Failed to connect to Steam API: {e}")
    except aiohttp.ClientTimeout as e:
        raise aiohttp.ClientTimeout(f"Steam API request timed out: {e}")
    except aiohttp.ClientError as e:
        raise aiohttp.ClientError(f"Network error contacting Steam API: {e}")

    if data["response"]["players"]:
        return data["response"]["players"][0]
    else:
        return None

@retry_with_exponential_backoff()
async def get_steam_emoticons(steam_id: str, session) -> Optional[List[Dict]]:
    """
    Fetch Steam emoticons for a given Steam ID.
    
    Args:
        steam_id: The 64-bit Steam ID of the user
        session: aiohttp ClientSession for making requests
        
    Returns:
        List of emoticon dictionaries or None if error
    """
    # Steam Community inventory URL
    # App ID 753 = Steam, Context 6 = Community items
    # Try different URL format to avoid potential 400 errors
    url = f"https://steamcommunity.com/inventory/{steam_id}/753/6"
    
    # Headers to mimic a browser request more closely
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }
    
    params = {
        'l': 'english',
        'count': 5000
    }
    
    try:
        logging.info(f"Fetching emoticons for Steam ID: {steam_id}")
        logging.info(f"Request URL: {url}")
        logging.info(f"Request params: {params}")
        
        async with session.get(url, headers=headers, params=params, allow_redirects=True) as response:
            if response.status != 200:
                response_text = await response.text()
                logging.warning(f"Steam inventory request failed with status {response.status} for {steam_id}. Response: {response_text[:200]}")
                return None
                
            data = await response.json()
            
            if not data.get('success'):
                logging.warning(f"Steam inventory API returned success=false for {steam_id}. Message: {data.get('Error', 'Unknown error')}")
                return None
                
            emoticons = []
            
            # Parse descriptions to find emoticons
            descriptions = data.get('descriptions', [])
            assets = data.get('assets', [])
            
            # Create a mapping of classid to description
            desc_map = {desc['classid']: desc for desc in descriptions}
            
            # Count quantities for each emoticon
            emoticon_counts = {}
            
            for asset in assets:
                classid = asset['classid']
                if classid in desc_map:
                    desc = desc_map[classid]
                    # Check if this is an emoticon
                    if desc.get('type') and 'Emoticon' in desc['type']:
                        key = (desc['market_name'], desc.get('type', ''), classid)
                        if key not in emoticon_counts:
                            emoticon_counts[key] = {
                                'name': desc['market_name'],
                                'type': desc.get('type', 'Emoticon'),
                                'game': desc.get('tags', [{}])[0].get('name', 'Unknown') if desc.get('tags') else 'Unknown',
                                'marketable': desc.get('marketable', 0),
                                'tradable': desc.get('tradable', 0),
                                'classid': classid,
                                'icon_url': f"https://community.cloudflare.steamstatic.com/economy/image/{desc.get('icon_url')}",
                                'quantity': 0
                            }
                        emoticon_counts[key]['quantity'] += int(asset.get('amount', 1))
            
            emoticons = list(emoticon_counts.values())
            logging.info(f"Found {len(emoticons)} unique emoticons for Steam ID: {steam_id}")
            
            return emoticons
            
    except aiohttp.ClientResponseError as e:
        logging.error(f"HTTP error fetching emoticons for {steam_id}: {e}")
        return None
    except aiohttp.ClientConnectorError as e:
        logging.error(f"Connection error fetching emoticons for {steam_id}: {e}")
        return None
    except aiohttp.ClientTimeout as e:
        logging.error(f"Timeout fetching emoticons for {steam_id}: {e}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error fetching emoticons for {steam_id}: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error fetching emoticons for {steam_id}: {e}")
        return None

async def get_player_avatars(steamid64, session):
    """
    Fetches player avatar URLs from Steam API
    Returns a dictionary with avatar URLs or None if not available
    """
    # Check cache first
    cache_key = steamid64
    if cache_key in _avatar_cache:
        cached_data, timestamp = _avatar_cache[cache_key]
        if time.time() - timestamp < _avatar_cache_ttl:
            return cached_data
    
    try:
        player_data = await get_player_summary(steamid64, session)
        
        if player_data:
            # Extract avatar URLs from the player data
            avatars = {
                "avatar": player_data.get("avatar", ""),  # 32x32
                "avatarmedium": player_data.get("avatarmedium", ""),  # 64x64
                "avatarfull": player_data.get("avatarfull", ""),  # 184x184
                "personaname": player_data.get("personaname", "Unknown"),  # Current display name
                "profileurl": player_data.get("profileurl", ""),  # Full profile URL
                "timecreated": player_data.get("timecreated", 0),  # Account creation timestamp
                "personastate": player_data.get("personastate", 0),  # Online status
                "communityvisibilitystate": player_data.get("communityvisibilitystate", 1)  # Profile visibility
            }
            
            # Cache the result
            _avatar_cache[cache_key] = (avatars, time.time())
            
            # Log avatar fetch for debugging
            logging.info(f"Fetched avatars for {steamid64}: {avatars['avatarfull'][:50]}...")
            
            return avatars
        else:
            logging.warning(f"No player data found for {steamid64}")
            return None
            
    except Exception as e:
        logging.error(f"Failed to fetch avatars for {steamid64}: {e}")
        return None

def serialize_avatar_data(avatar_data):
    """
    Serializes avatar data to JSON string for database storage
    """
    if avatar_data:
        return json.dumps(avatar_data)
    return json.dumps({})

def deserialize_avatar_data(avatar_json):
    """
    Deserializes avatar data from JSON string
    """
    if avatar_json:
        try:
            return json.loads(avatar_json)
        except json.JSONDecodeError:
            logging.error(f"Failed to deserialize avatar data: {avatar_json}")
            return {}
    return {}