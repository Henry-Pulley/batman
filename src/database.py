"""PostgreSQL database storage with connection pooling for Steam Analyzer"""
import logging
import os
import time
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DatabasePool:
    """Singleton database connection pool manager"""
    _instance = None
    _lock = threading.Lock()
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the connection pool once"""
        if self._pool is None:
            self._initialize_pool()

    def _initialize_pool(self):
        """Create the connection pool"""
        try:
            # Get configuration from environment
            min_conn = int(os.getenv("POSTGRES_POOL_MIN", "2"))
            max_conn = int(os.getenv("POSTGRES_POOL_MAX", "20"))

            self._pool = psycopg2.pool.ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                database=os.getenv("POSTGRES_DATABASE", "steam_analyzer"),
                user=os.getenv("POSTGRES_USER", ""),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                cursor_factory=RealDictCursor
            )
            logging.info(f"Database pool initialized with {min_conn}-{max_conn} connections")

            # Create tables on initialization
            self._create_tables()

        except psycopg2.OperationalError as e:
            logging.error(f"Failed to initialize database pool: {e}")
            raise

    def _create_tables(self):
        """Create database schema using a connection from the pool"""
        conn = None
        try:
            conn = self._pool.getconn()
            with conn.cursor() as cursor:
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
                    last_checked TIMESTAMP,
                    user_notes TEXT
                );

                -- Create indexes for better performance
                CREATE INDEX IF NOT EXISTS idx_commenter_steamid ON flagged_comments(commenter_steamid);
                CREATE INDEX IF NOT EXISTS idx_profile_steamid ON flagged_comments(profile_steamid);
                CREATE INDEX IF NOT EXISTS idx_villain_steamid ON villains(steam_id);
                CREATE INDEX IF NOT EXISTS idx_unprocessed_steamid ON unprocessed_profiles(steam_id);
                CREATE INDEX IF NOT EXISTS idx_reported_steamid ON reported_profiles(steam_id);
                CREATE INDEX IF NOT EXISTS idx_reported_comment_id ON reported_profiles(comment_id);
                CREATE INDEX IF NOT EXISTS idx_monitoring_steamid ON further_monitoring(steam_id);
                """

                cursor.execute(schema)
                conn.commit()
                logging.info("Database schema verified/created")

        except Exception as e:
            logging.error(f"Failed to create database schema: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool with automatic cleanup"""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._pool.putconn(conn)

    def close_all(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()
            logging.info("Database pool closed")

    def get_pool_status(self):
        """Get current pool statistics"""
        if self._pool:
            # Note: psycopg2's pool doesn't expose these directly,
            # but we can infer from the internal state
            return {
                "closed": self._pool.closed,
                "min_connections": self._pool.minconn,
                "max_connections": self._pool.maxconn
            }
        return None

class PostgresDatabase:
    """
    Database interface with connection pooling.
    Maintains backwards compatibility with existing code.
    """

    def __init__(self):
        self.pool = DatabasePool()
        self.conn = None
        self.cursor = None
        self._in_context = False

    def __enter__(self):
        """Enter context manager - get connection from pool"""
        self._in_context = True
        self._ctx_manager = self.pool.get_connection()
        self.conn = self._ctx_manager.__enter__()
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - return connection to pool"""
        self._in_context = False
        if self.cursor:
            self.cursor.close()
            self.cursor = None

        # Let the context manager handle the connection
        if hasattr(self, '_ctx_manager'):
            self._ctx_manager.__exit__(exc_type, exc_val, exc_tb)

        self.conn = None

    def connect(self):
        """Legacy method for backwards compatibility"""
        if not self._in_context:
            logging.warning("Direct connect() called - consider using context manager")
            self.__enter__()

    def close(self):
        """Legacy method for backwards compatibility"""
        if not self._in_context and self.conn:
            logging.warning("Direct close() called - consider using context manager")
            self.__exit__(None, None, None)

    def create_tables(self):
        """Tables are created automatically by the pool"""
        pass

    def insert_flagged_comment(self, comment_data):
        """
        Inserts a flagged comment if it doesn't already exist
        Returns: bool - True if inserted, False if already exists
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
        Returns: int - Number of comments inserted
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
            query = """
            INSERT INTO flagged_comments
            (commenter_steamid, commenter_alias, profile_steamid,
            comment_text, comment_date, friend_path)
            VALUES %s
            ON CONFLICT (commenter_steamid, profile_steamid, comment_text) DO NOTHING
            """

            execute_values(self.cursor, query, values)
            inserted_count = self.cursor.rowcount
            self.conn.commit()

            logging.info(f"Batch inserted {inserted_count} flagged comments")
            return inserted_count

        except psycopg2.Error as e:
            logging.error(f"Failed to batch insert flagged comments: {e}")
            self.conn.rollback()
            return 0

    def get_all_flagged_comments_detailed(self):
        """Returns all flagged comments with full details"""
        query = "SELECT * FROM flagged_comments ORDER BY comment_scraped DESC"
        try:
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except psycopg2.Error as e:
            logging.error(f"Failed to get detailed flagged comments: {e}")
            return []

    def insert_villain(self, steam_id, aliases):
        """Insert or update a villain"""
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
        """Retrieves a villain by Steam ID"""
        try:
            query = "SELECT * FROM villains WHERE steam_id = %s"
            self.cursor.execute(query, (steam_id,))
            return self.cursor.fetchone()
        except psycopg2.Error as e:
            logging.error(f"Failed to get villain: {e}")
            return None

    def get_all_villains(self):
        """Returns all villains"""
        try:
            query = "SELECT * FROM villains ORDER BY id"
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except psycopg2.Error as e:
            logging.error(f"Failed to get all villains: {e}")
            return []

    def get_report_data(self):
        """Fetches all data needed for report generation"""
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
        """Checks if a Steam ID is in the villains table"""
        villain = self.get_villain(steam_id)
        return villain is not None

    def save_unprocessed_profiles(self, profiles_data, shutdown_reason):
        """Saves unprocessed profiles to the database"""
        if not profiles_data:
            return 0

        try:
            # Prepare data for bulk insert
            values = []
            for steam_id, friend_path, depth in profiles_data:
                values.append((steam_id, friend_path, depth, shutdown_reason))

            # Use execute_values for efficient bulk insert
            query = """
            INSERT INTO unprocessed_profiles (steam_id, friend_path, depth, shutdown_reason)
            VALUES %s
            ON CONFLICT (steam_id, friend_path) DO NOTHING
            """

            execute_values(self.cursor, query, values)
            inserted_count = self.cursor.rowcount
            self.conn.commit()

            logging.info(f"Saved {inserted_count} unprocessed profiles due to {shutdown_reason}")
            return inserted_count

        except psycopg2.Error as e:
            logging.error(f"Failed to save unprocessed profiles: {e}")
            self.conn.rollback()
            return 0

    def get_unprocessed_profiles_count(self):
        """Returns the count of unprocessed profiles"""
        try:
            query = "SELECT COUNT(*) as count FROM unprocessed_profiles"
            self.cursor.execute(query)
            result = self.cursor.fetchone()
            return result['count'] if result else 0
        except psycopg2.Error as e:
            logging.error(f"Failed to get unprocessed profiles count: {e}")
            return 0

# Utility functions for connection pool management

def get_pool_status():
    """Get the current status of the database connection pool"""
    pool = DatabasePool()
    return pool.get_pool_status()

def cleanup_database_pool():
    """Close all connections in the pool (for shutdown)"""
    pool = DatabasePool()
    pool.close_all()

# Performance monitoring wrapper

class MonitoredDatabase(PostgresDatabase):
    """Database wrapper with performance monitoring"""

    def __init__(self):
        super().__init__()
        self.query_times = []

    def execute_with_timing(self, query, params=None):
        """Execute query and track timing"""
        start_time = time.time()
        try:
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)

            elapsed = time.time() - start_time
            self.query_times.append({
                'query': query[:50] + '...' if len(query) > 50 else query,
                'time': elapsed
            })

            if elapsed > 1.0:  # Log slow queries
                logging.warning(f"Slow query ({elapsed:.2f}s): {query[:100]}...")

        except Exception as e:
            elapsed = time.time() - start_time
            logging.error(f"Query failed after {elapsed:.2f}s: {e}")
            raise

    def get_performance_stats(self):
        """Get performance statistics"""
        if not self.query_times:
            return None

        times = [q['time'] for q in self.query_times]
        return {
            'total_queries': len(times),
            'total_time': sum(times),
            'avg_time': sum(times) / len(times),
            'max_time': max(times),
            'slow_queries': [q for q in self.query_times if q['time'] > 1.0]
        }