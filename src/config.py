"""Configuration settings for Steam Comment Analyzer"""

import re
from typing import List, Pattern
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    # Steam API configuration
    steam_api_key: str = Field(default="")
    steam_api_base: str = "https://api.steampowered.com"

    # Rate limiting
    request_delay: float = 5.0
    max_retries: int = 3
    max_concurrent_requests: int = 3
    semaphore_timeout: float = 30.0

    # Hate terms list (example - should be expanded)
    hate_terms: List[str] = [
        # Keywords - Add your own terms here
        "boop",
        "offensive_phrase",
        # Unicode characters/emoticons
        "🚫", "⛔",
    ]
    
    # Regex patterns for more complex matching (separate from simple terms)
    hate_regex_patterns: List[str] = [
        r"\b(pattern1|pattern2)\b",
    ]
    
    # Compiled regex patterns (initialized at runtime)
    _compiled_patterns: List[Pattern] = []

    # Logging
    log_level: str = "INFO"
    log_file: str = "output/steam_analyzer.log"

    # Target URLs to analyze
    target_urls: List[str] = [
        "https://steamcommunity.com/profiles/76561198056686440"
    ]

    @validator('request_delay')
    def validate_request_delay(cls, v):
        if v < 0:
            raise ValueError('Request delay must be non-negative')
        return v

    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0:
            raise ValueError('Max retries must be non-negative')
        return v

    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {", ".join(valid_levels)}')
        return v.upper()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


def compile_hate_patterns():
    """
    Compiles regex patterns for hate speech detection at startup.
    This improves performance by avoiding repeated compilation during runtime.
    """
    global config
    config._compiled_patterns = []
    
    for pattern_str in config.hate_regex_patterns:
        try:
            compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
            config._compiled_patterns.append(compiled_pattern)
        except re.error as e:
            import logging
            logging.warning(f"Invalid regex pattern '{pattern_str}': {e}")

def get_compiled_patterns() -> List[Pattern]:
    """Returns the list of compiled regex patterns"""
    return config._compiled_patterns

# Create a global config instance
config = Config()