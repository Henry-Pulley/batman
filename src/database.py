"""PostgreSQL database storage and management for flagged comments"""
import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class PostgresDatabase:
    def __init__(self):
        self.conn = None
        self.cursor = None

    def __enter__(self):
        """Establish connection when entering context."""
        self.connect()
        self.create_tables()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close connection when exiting context."""
        self.close()
    
    def connect(self):
        """Establishes connection to PostgreSQL database"""
        try:
            self.conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                database=os.getenv("POSTGRES_DATABASE", "steam_analyzer"),
                user=os.getenv("POSTGRES_USER", ""),
                password=os.getenv("POSTGRES_PASSWORD", "")
            )
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            logging.info("Connected to PostgreSQL database")
        except psycopg2.OperationalError as e:
            logging.error(f"Database connection failed - server unavailable or credentials invalid: {e}")
            raise psycopg2.OperationalError(f"Database connection failed: {e}")
        except psycopg2.DatabaseError as e:
            logging.error(f"Database error during connection: {e}")
            raise psycopg2.DatabaseError(f"Database connection error: {e}")
        except ValueError as e:
            logging.error(f"Invalid database configuration: {e}")
            raise ValueError(f"Invalid database configuration: {e}")
        except Exception as e:
            logging.error(f"Unexpected error connecting to database: {e}")
            raise psycopg2.Error(f"Unexpected database connection error: {e}")

    def create_tables(self):
        """Creates the database schema"""
        schema = """
        CREATE TABLE IF NOT EXISTS flagged_comments (
            id SERIAL PRIMARY KEY,
            commenter_steamid VARCHAR(50) NOT NULL,
            commenter_alias VARCHAR(255) NOT NULL,
            profile_steamid VARCHAR(50) NOT NULL,
            comment_text TEXT NOT NULL,
            comment_date TIMESTAMP,
            friend_path TEXT NOT NULL,
            comment_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(commenter_steamid, profile_steamid, comment_text)
        );

        CREATE TABLE IF NOT EXISTS villains (
            id SERIAL PRIMARY KEY,
            steam_id VARCHAR(17) UNIQUE NOT NULL,
            aliases TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS unprocessed_profiles (
            id SERIAL PRIMARY KEY,
            steam_id VARCHAR(17) NOT NULL,
            friend_path TEXT NOT NULL,
            depth INTEGER NOT NULL,
            added_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            shutdown_reason VARCHAR(100) NOT NULL,
            UNIQUE(steam_id, friend_path)
        );

        CREATE TABLE IF NOT EXISTS reported_profiles (
            id SERIAL PRIMARY KEY,
            steam_id VARCHAR(17) NOT NULL,
            alias VARCHAR(255) NOT NULL,
            comment_id INTEGER REFERENCES flagged_comments(id),
            status VARCHAR(50) DEFAULT 'pending manual review',
            screenshot_path TEXT,
            reported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS further_monitoring (
            id SERIAL PRIMARY KEY,
            steam_id VARCHAR(17) UNIQUE NOT NULL,
            alias VARCHAR(255) NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked TIMESTAMP
        );
        """
        
        try:
            self.cursor.execute(schema)
            
            # Create indexes for better performance
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_commenter_steamid ON flagged_comments(commenter_steamid)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_profile_steamid ON flagged_comments(profile_steamid)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_villain_steamid ON villains(steam_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_unprocessed_steamid ON unprocessed_profiles(steam_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_reported_steamid ON reported_profiles(steam_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_reported_comment_id ON reported_profiles(comment_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_steamid ON further_monitoring(steam_id)"
            )
            
            self.conn.commit()
            logging.info("Database schema created successfully")
        except psycopg2.Error as e:
            logging.error(f"Failed to create database schema: {e}")
            self.conn.rollback()
            raise

    def insert_flagged_comment(self, comment_data):
        """
        Inserts a flagged comment if it doesn't already exist

        Returns:
            bool: True if inserted, False if already exists
        """
        try:
            query = """
            INSERT INTO flagged_comments
            (commenter_steamid, commenter_alias, profile_steamid,
             comment_text, comment_date, friend_path)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (commenter_steamid, profile_steamid, comment_text) DO NOTHING
            RETURNING id
            """
            self.cursor.execute(query, (
                comment_data['commenter_steamid'],
                comment_data['commenter_alias'],
                comment_data['profile_steamid'],
                comment_data['comment_text'],
                comment_data['comment_date'],
                comment_data['friend_path']
            ))
            
            result = self.cursor.fetchone()
            self.conn.commit()
            
            return result is not None
        except psycopg2.Error as e:
            logging.error(f"Failed to insert flagged comment: {e}")
            self.conn.rollback()
            return False

    
    def insert_flagged_comments_batch(self, comments_data_list):
        """
        Batch insert multiple flagged comments for better performance
        
        Args:
            comments_data_list: List of comment data dictionaries
            
        Returns:
            int: Number of comments inserted
        """
        if not comments_data_list:
            return 0
            
        try:
            # Prepare data for bulk insert
            values = []
            for comment_data in comments_data_list:
                values.append((
                    comment_data['commenter_steamid'],
                    comment_data['commenter_alias'],
                    comment_data['profile_steamid'],
                    comment_data['comment_text'],
                    comment_data['comment_date'],
                    comment_data['friend_path']
                ))
            
            # Use execute_values for efficient bulk insert
            from psycopg2.extras import execute_values
            
            query = """
            INSERT INTO flagged_comments
            (commenter_steamid, commenter_alias, profile_steamid,
            comment_text, comment_date, friend_path)
            VALUES %s
            ON CONFLICT (commenter_steamid, profile_steamid, comment_text) DO NOTHING
            """
            
            execute_values(self.cursor, query, values)
            self.conn.commit()
            
            return len(values)
        except psycopg2.Error as e:
            logging.error(f"Failed to batch insert flagged comments: {e}")
            self.conn.rollback()
            return 0
    
    def get_all_flagged_comments_detailed(self):
        """
        Returns all flagged comments with full details for viewing
        
        Returns:
            list: List of flagged comment records with all fields
        """
        query = "SELECT * FROM flagged_comments ORDER BY comment_scraped DESC"
        try:
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except psycopg2.Error as e:
            logging.error(f"Failed to get detailed flagged comments: {e}")
            return []

    def insert_villain(self, steam_id, aliases):
        """
        Inserts a villain if it doesn't already exist
        
        Args:
            steam_id (str): 17-digit Steam ID
            aliases (str): Comma-separated list of Steam aliases
            
        Returns:
            bool: True if inserted, False if already exists
        """
        try:
            query = """
            INSERT INTO villains (steam_id, aliases)
            VALUES (%s, %s)
            ON CONFLICT (steam_id) DO UPDATE SET aliases = EXCLUDED.aliases
            RETURNING id
            """
            self.cursor.execute(query, (steam_id, aliases))
            
            result = self.cursor.fetchone()
            self.conn.commit()
            
            return result is not None
        except psycopg2.Error as e:
            logging.error(f"Failed to insert villain: {e}")
            self.conn.rollback()
            return False

    def get_villain(self, steam_id):
        """
        Retrieves a villain by Steam ID
        
        Args:
            steam_id (str): 17-digit Steam ID
            
        Returns:
            dict or None: Villain data if found, None otherwise
        """
        try:
            query = "SELECT * FROM villains WHERE steam_id = %s"
            self.cursor.execute(query, (steam_id,))
            return self.cursor.fetchone()
        except psycopg2.Error as e:
            logging.error(f"Failed to get villain: {e}")
            return None

    def get_all_villains(self):
        """
        Returns all villains
        
        Returns:
            list: List of villain records
        """
        try:
            query = "SELECT * FROM villains ORDER BY id"
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except psycopg2.Error as e:
            logging.error(f"Failed to get all villains: {e}")
            return []

    def get_report_data(self):
        """
        Fetches all data needed for report generation in a single method
        
        Returns:
            dict: Contains statistics, villains, and flagged comments
        """
        try:
            # Get statistics
            self.cursor.execute("SELECT COUNT(*) as total_comments FROM flagged_comments")
            total_comments = self.cursor.fetchone()['total_comments']

            self.cursor.execute("SELECT COUNT(DISTINCT commenter_steamid) as unique_commenters FROM flagged_comments")
            unique_commenters = self.cursor.fetchone()['unique_commenters']

            # Get all villains
            self.cursor.execute("SELECT * FROM villains ORDER BY id")
            villains = self.cursor.fetchall()

            # Get all flagged comments
            query = """
            SELECT commenter_steamid, commenter_alias,
                   profile_steamid, friend_path, comment_text
            FROM flagged_comments
            ORDER BY comment_scraped DESC
            """
            self.cursor.execute(query)
            flagged_comments = [(row['commenter_steamid'], row['commenter_alias'], 
                               row['profile_steamid'], row['friend_path'], 
                               row['comment_text']) for row in self.cursor.fetchall()]

            return {
                'statistics': {
                    'total_comments': total_comments,
                    'unique_commenters': unique_commenters
                },
                'villains': villains,
                'flagged_comments': flagged_comments
            }
        except psycopg2.Error as e:
            logging.error(f"Failed to get report data: {e}")
            return {
                'statistics': {
                    'total_comments': 0,
                    'unique_commenters': 0
                },
                'villains': [],
                'flagged_comments': []
            }

    def is_villain(self, steam_id):
        """
        Checks if a Steam ID is in the villains table
        
        Args:
            steam_id (str): 17-digit Steam ID
            
        Returns:
            bool: True if villain exists, False otherwise
        """
        villain = self.get_villain(steam_id)
        return villain is not None

    def save_unprocessed_profiles(self, profiles_data, shutdown_reason):
        """
        Saves unprocessed profiles to the database
        
        Args:
            profiles_data (list): List of tuples (steam_id, friend_path, depth)
            shutdown_reason (str): Reason for shutdown (e.g., "profile_limit", "time_limit")
            
        Returns:
            int: Number of profiles saved
        """
        if not profiles_data:
            return 0
            
        try:
            # Prepare data for bulk insert
            values = []
            for steam_id, friend_path, depth in profiles_data:
                values.append((steam_id, friend_path, depth, shutdown_reason))
            
            # Use execute_values for efficient bulk insert
            from psycopg2.extras import execute_values
            
            query = """
            INSERT INTO unprocessed_profiles (steam_id, friend_path, depth, shutdown_reason)
            VALUES %s
            ON CONFLICT (steam_id, friend_path) DO NOTHING
            """
            
            execute_values(self.cursor, query, values)
            self.conn.commit()
            
            logging.info(f"Saved {len(values)} unprocessed profiles due to {shutdown_reason}")
            return len(values)
        except psycopg2.Error as e:
            logging.error(f"Failed to save unprocessed profiles: {e}")
            self.conn.rollback()
            return 0

    def get_unprocessed_profiles_count(self):
        """
        Returns the count of unprocessed profiles
        
        Returns:
            int: Number of unprocessed profiles
        """
        try:
            query = "SELECT COUNT(*) as count FROM unprocessed_profiles"
            self.cursor.execute(query)
            result = self.cursor.fetchone()
            return result['count'] if result else 0
        except psycopg2.Error as e:
            logging.error(f"Failed to get unprocessed profiles count: {e}")
            return 0

    def close(self):
        """Closes the database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logging.info("PostgreSQL connection closed")