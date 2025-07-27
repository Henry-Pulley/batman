from typing import Optional, Tuple
import re
from urllib.parse import urlparse
import ipaddress

class SafetyValidator:
    """Multi-layer input validation for safety."""

    # Known Steam URL patterns
    VALID_STEAM_PATTERNS = [
        r'^https?://steamcommunity\.com/id/[a-zA-Z0-9_-]+/?$',
        r'^https?://steamcommunity\.com/profiles/\d{17}/?$'
    ]

    # Blacklisted IDs (known bad actors, test accounts, etc.)
    BLACKLISTED_IDS = set()

    # Rate limit per domain
    DOMAIN_LIMITS = {
        'steamcommunity.com': 100,  # requests per minute
        'default': 50
    }

    def __init__(self):
        self.compiled_patterns = [re.compile(p) for p in self.VALID_STEAM_PATTERNS]

    def validate_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """Validate URL with multiple safety checks."""
        # Length check
        if len(url) > 500:
            return False, "URL too long"

        # Pattern matching
        if not any(p.match(url) for p in self.compiled_patterns):
            return False, "Invalid Steam URL format"

        # Parse URL safely
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False, "Invalid URL scheme"

            # Check for localhost/private IPs (SSRF prevention)
            if self._is_private_ip(parsed.hostname):
                return False, "Private IP addresses not allowed"

            # Extract Steam ID
            steamid = self._extract_steamid(url)
            if steamid in self.BLACKLISTED_IDS:
                return False, "Blacklisted Steam ID"

        except Exception as e:
            return False, f"URL parsing error: {e}"

        return True, None

    def _is_private_ip(self, hostname: Optional[str]) -> bool:
        """Check if hostname resolves to private IP."""
        if not hostname:
            return False

        try:
            # Resolve hostname
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback
        except:
            # Not an IP address, continue
            pass

        # Additional checks for common private hostnames
        private_hostnames = ['localhost', '127.0.0.1', '0.0.0.0']
        return hostname.lower() in private_hostnames

    def _extract_steamid(self, url: str) -> Optional[str]:
        """Safely extract Steam ID from URL."""
        if '/profiles/' in url:
            match = re.search(r'/profiles/(\d{17})', url)
            return match.group(1) if match else None
        elif '/id/' in url:
            match = re.search(r'/id/([a-zA-Z0-9_-]+)', url)
            return match.group(1) if match else None
        return None