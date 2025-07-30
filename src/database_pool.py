import psycopg2
from psycopg2 import pool
import logging
from contextlib import contextmanager
from .config import config

class DatabasePool:
    """PostgreSQL connection pool for better performance"""
    
    def __init__(self):
        self._pool = None
        self._create_pool()
    
    def _create_pool(self):
        """Create the connection pool"""
        try:
            self._pool = pool.ThreadedConnectionPool(
                config.postgres_pool_min,
                config.postgres_pool_max,
                host=config.postgres_host,
                port=config.postgres_port,
                database=config.postgres_database,
                user=config.postgres_user,
                password=config.postgres_password
            )
            logging.info(f"Created PostgreSQL connection pool (min={config.postgres_pool_min}, max={config.postgres_pool_max})")
        except Exception as e:
            logging.error(f"Failed to create connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool"""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn and self._pool:
                self._pool.putconn(conn)
    
    def close_all(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()

# Global pool instance
db_pool = DatabasePool()
