#!/usr/bin/env python3
"""
Clear flagged comments from a specific profile for debugging
"""

from src.database import PostgresDatabase

def clear_profile_comments(profile_steamid):
    with PostgresDatabase() as db:
        # Delete flagged comments from this profile
        db.cursor.execute("DELETE FROM flagged_comments WHERE profile_steamid = %s", (profile_steamid,))
        deleted_count = db.cursor.rowcount
        db.conn.commit()
        
        print(f"Deleted {deleted_count} flagged comments from profile {profile_steamid}")
        
        # Verify deletion
        db.cursor.execute("SELECT COUNT(*) as count FROM flagged_comments WHERE profile_steamid = %s", (profile_steamid,))
        result = db.cursor.fetchone()
        remaining = result['count'] if result else 0
        print(f"Remaining comments from this profile: {remaining}")

if __name__ == "__main__":
    profile_id = "76561198056686440"  # The profile you're testing
    clear_profile_comments(profile_id)