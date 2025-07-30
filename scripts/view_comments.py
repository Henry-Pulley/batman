#!/usr/bin/env python3
"""Simple script to view all flagged comments from the database"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.database import PostgresDatabase

def view_all_comments():
    with PostgresDatabase() as db:
        try:
            comments = db.get_all_flagged_comments_detailed()
            
            if not comments:
                print("No flagged comments found in database.")
                return
            
            print(f"Found {len(comments)} flagged comment(s):\n")
            print("=" * 80)
            
            for comment in comments:
                print(f"ID:                {comment['id']}")
                print(f"Commenter SteamID: {comment['profile_steamid']}")
                print(f"Commenter Alias:   \033[42m{comment['commenter_alias']}\033[0m")
                print(f"Friend Path:       {comment['friend_path']}")
                print(f"Comment:           \033[43m{comment['comment_text']}\033[0m")
                # Format the comment_date timestamp
                comment_dt = comment['comment_date']
                comment_date = comment_dt.strftime('%Y-%m-%d')
                comment_time = comment_dt.strftime('%I:%M %p')
                print(f"Comment Date:      {comment_date} at {comment_time}")
                # Format the comment_scraped timestamp
                scraped_dt = comment['comment_scraped']
                scraped_date = scraped_dt.strftime('%Y-%m-%d')
                scraped_time = scraped_dt.strftime('%I:%M %p')
                print(f"Comment Scraped:   {scraped_date} at {scraped_time}")
                print("=" * 80)
                
        except Exception as e:
            print(f"Error retrieving comments: {e}")

if __name__ == "__main__":
    view_all_comments()