# README.md

This file provides guidance when working with code in this repository.

## Project Overview

This is a Steam Comment Analyzer tool designed for defensive security purposes - to help identify and track hate speech or offensive content on Steam profiles. It recursively searches Steam profiles starting from a given URL and stores flagged comments in a PostgreSQL database.

## Development Commands

```bash
# ALWAYS activate virtual environment before running any Python commands
source .venv/bin/activate

# Use python3 instead of python
# Use pip3 instead of pip
# Install dependencies if needed
pip3 install -r requirements.txt
```

### Running the Application

```bash
# ALWAYS ensure virtual environment is activated first
source .venv/bin/activate

# Run using target URLs from config.py (recommended approach)
python3 main.py

# Or run with a specific Steam profile URL to override config
python3 main.py https://steamcommunity.com/id/username # the system will get the current username associated with the comment
# or
python3 main.py https://steamcommunity.com/profiles/steamid64 # steamid64 are integer IDs that are 17 digits long
```

**Note**: By default, the application uses the URLs specified in `src/config.py` under `target_urls`. You can add multiple URLs to analyze in that list, or pass a single URL as a command line argument to override the config.

## Architecture

### Core Components

- **main.py**: Entry point that validates input and initiates the recursive search
- **config.py**: Central configuration including API keys, rate limits, and hate terms
- **recursive_search.py**: Main recursive search logic using a queue-based approach to traverse profiles
- **steam_api.py**: Steam Web API integration for resolving profile URLs
- **scraper.py**: Web scraping logic to extract comments from Steam profile pages
- **database.py**: PostgreSQL database management for storing flagged comments with RealDictCursor and ON CONFLICT handling
- **report.py**: Report generation and network visualization

### Key Design Patterns

- **Queue-based traversal**: Uses a Queue to manage profiles to visit, avoiding deep recursion
- **Rate limiting**: Respects Steam's servers with configurable delays between requests
- **Set tracking**: Maintains visited and queued sets to avoid duplicate processing
- **Path tracking**: Records the path from initial profile to each discovered profile

### Data Flow

1. URL validation and Steam ID resolution
2. Queue-based breadth-first search of profiles
3. Comment scraping and hate speech detection
4. Database storage of flagged comments with metadata
5. Network visualization generation showing profile connections

### Output Files

- PostgreSQL database with flagged comments (configured in config.py)
- `steam_comment_network.png`: Network visualization
- `steam_analyzer.log`: Detailed operation logs
