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
    request_delay: float = Field(default=0.5, alias='REQUEST_DELAY') # work towards 0.1
    max_retries: int = Field(default=2, alias='MAX_RETRIES')
    max_concurrent_requests: int = Field(default=10, alias='MAX_CONCURRENT_REQUESTS') # work towards 50
    semaphore_timeout: float = Field(default=30.0, alias='SEMAPHORE_TIMEOUT')

    # Connection settings
    connection_pool_size: int = Field(default=100, alias='CONNECTION_POOL_SIZE')
    keepalive_timeout: int = Field(default=30, alias='KEEPALIVE_TIMEOUT')
    
    # Database connection pool (new)
    postgres_pool_min: int = Field(default=5, alias='POSTGRES_POOL_MIN')
    postgres_pool_max: int = Field(default=20, alias='POSTGRES_POOL_MAX')
    
    # Database connection settings
    postgres_host: str = Field(default="localhost", alias='POSTGRES_HOST')
    postgres_port: int = Field(default=5432, alias='POSTGRES_PORT')
    postgres_database: str = Field(default="steam_analyzer", alias='POSTGRES_DATABASE')
    postgres_user: str = Field(default="", alias='POSTGRES_USER')
    postgres_password: str = Field(default="", alias='POSTGRES_PASSWORD')

    # Friends list configuration
    max_friends_per_profile: int = 50
    
    # Processing limits
    max_profiles_to_process: int = Field(default=100, alias='MAX_PROFILES_TO_PROCESS')  # 0 = unlimited
    max_processing_time_minutes: int = Field(default=5, alias='MAX_PROCESSING_TIME_MINUTES')  # 0 = unlimited

    # Hate terms list (example - should be expanded)
    hate_terms: List[str] = [
        # Keywords - Add your own terms here
        "libs", "liberals", "libtard", "libtards", "libtardism", "libtardist", "libtardists", "tard", "tards", "retard", "retards", "ret4rd", "ret4rds"
    ]
    
    # Regex patterns for more complex matching (separate from simple terms)
    hate_regex_patterns: List[str] = []
    
    # Compiled regex patterns (initialized at runtime)
    _compiled_patterns: List[Pattern] = []

    # Logging
    log_level: str = "INFO"
    log_file: str = "output/steam_analyzer.log"

    # Target URLs to analyze
    target_urls: List[str] = [
        "https://steamcommunity.com/id/14Maverick"
    ]

    @validator('max_concurrent_requests')
    def validate_concurrent_requests(cls, v):
        if v < 1:
            raise ValueError('Max concurrent requests must be at least 1')
        if v > 200:
            raise ValueError('Max concurrent requests should not exceed 200')
        return v

    @validator('connection_pool_size')
    def validate_connection_pool(cls, v, values):
        max_concurrent = values.get('max_concurrent_requests', 50)
        if v < max_concurrent:
            # Pool should be at least as large as concurrent requests
            return max_concurrent * 2
        return v

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

    @validator('max_profiles_to_process')
    def validate_max_profiles(cls, v):
        if v < 0:
            raise ValueError('Max profiles to process must be non-negative (0 = unlimited)')
        return v

    @validator('max_processing_time_minutes')
    def validate_max_processing_time(cls, v):
        if v < 0:
            raise ValueError('Max processing time must be non-negative (0 = unlimited)')
        return v

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