"""Steam API integration and profile resolution functions"""

import asyncio
import aiohttp
from .config import config
from .retry_utils import retry_with_exponential_backoff

async def resolve_steam_url(url, session):
    """
    Resolves a Steam profile URL to a SteamID64

    Args:
        url: Steam profile URL
        session: aiohttp session (required)

    Returns:
        steamid64: 64-bit Steam ID
    """
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
        return identifier
    else:
        # Assume it's an alias
        return await resolve_vanity_url(identifier, session)

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

    try:
        async with session.get(endpoint, params=params) as response:
            if response.status != 200:
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Steam API returned status {response.status}"
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

    try:
        async with session.get(endpoint, params=params) as response:
            if response.status != 200:
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=response.history,
                    status=response.status,
                    message=f"Steam API returned status {response.status}"
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