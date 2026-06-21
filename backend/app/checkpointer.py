import os
import logging
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres_dev_pass@postgres:5432/repo_intel"
)

pool = None
checkpointer = None

def get_checkpointer():
    global pool, checkpointer
    if checkpointer is None:
        try:
            logger.info("Initializing PostgresSaver checkpointer connection pool...")
            # Initialize psycopg3 connection pool
            pool = ConnectionPool(
                conninfo=DATABASE_URL,
                max_size=10,
                min_size=1,
                kwargs={"autocommit": True}
            )
            # Create the PostgresSaver checkpointer using the connection pool
            checkpointer = PostgresSaver(pool)
            
            # Setup checkpointer tables in the database if they don't exist
            logger.info("Setting up LangGraph checkpointer tables in PostgreSQL...")
            checkpointer.setup()
            logger.info("LangGraph checkpointer tables setup completed successfully.")
        except Exception as e:
            logger.exception(f"Failed to initialize PostgresSaver checkpointer: {e}")
            raise e
    return checkpointer
