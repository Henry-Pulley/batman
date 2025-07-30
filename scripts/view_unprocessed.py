#!/usr/bin/env python3
"""Script to view unprocessed profiles from the database"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database import PostgresDatabase

def main():
    with PostgresDatabase() as db:
        # Get count of unprocessed profiles
        count = db.get_unprocessed_profiles_count()
        
        if count == 0:
            print("No unprocessed profiles found.")
            return
        
        print(f"Found {count} unprocessed profile(s):")
        print("=" * 80)
        
        # Get all unprocessed profiles
        try:
            db.cursor.execute("""
                SELECT steam_id, friend_path, depth, shutdown_reason, added_timestamp
                FROM unprocessed_profiles 
                ORDER BY added_timestamp DESC
            """)
            results = db.cursor.fetchall()
            
            for row in results:
                print(f"Steam ID:        {row['steam_id']}")
                print(f"Friend Path:     {row['friend_path']}")
                print(f"Depth:           {row['depth']}")
                print(f"Shutdown Reason: {row['shutdown_reason']}")
                print(f"Added:           {row['added_timestamp']}")
                print("-" * 80)
                
        except Exception as e:
            print(f"Error fetching unprocessed profiles: {e}")

if __name__ == "__main__":
    main()