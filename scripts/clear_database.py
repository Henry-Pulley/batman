#!/usr/bin/env python3
"""Clear all data from the Steam Analyzer database"""

import logging
import sys
import os

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import PostgresDatabase

def clear_database():
    """Clear all data from both flagged_comments and villains tables"""
    try:
        with PostgresDatabase() as db:
            # Clear flagged_comments table
            db.cursor.execute("DELETE FROM flagged_comments")
            comments_deleted = db.cursor.rowcount
            
            # Clear villains table
            db.cursor.execute("DELETE FROM villains")
            villains_deleted = db.cursor.rowcount
            
            # Commit the changes
            db.conn.commit()
            
            print(f"Database cleared successfully:")
            print(f"- Deleted {comments_deleted} flagged comments")
            print(f"- Deleted {villains_deleted} villains")
            
            return True
            
    except Exception as e:
        print(f"Error clearing database: {e}")
        return False

if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(level=logging.INFO)
    
    print("Clearing Steam Analyzer database...")
    
    # Ask for confirmation
    response = input("Are you sure you want to clear ALL data from the database? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Operation cancelled.")
        sys.exit(0)
    
    success = clear_database()
    sys.exit(0 if success else 1)