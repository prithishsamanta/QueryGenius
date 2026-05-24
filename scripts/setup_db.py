#!/usr/bin/env python3
"""
Setup PostgreSQL database with pgvector extension.

Run this script once to initialize the database schema.
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from src.models.schemas import Base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_database():
    """Initialize database schema and pgvector extension."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    engine = create_engine(database_url)

    # Create pgvector extension
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            print("✓ pgvector extension created")
        except Exception as e:
            print(f"✗ Failed to create pgvector extension: {e}")
            raise

    # Create all tables
    try:
        Base.metadata.create_all(engine)
        print("✓ Database tables created")
    except Exception as e:
        print(f"✗ Failed to create tables: {e}")
        raise

    # Create vector index
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS queries_embedding_idx "
                "ON queries USING ivfflat (embedding vector_cosine_ops) "
                "WITH (lists = 100);"
            ))
            conn.commit()
            print("✓ Vector similarity index created")
        except Exception as e:
            print(f"✗ Failed to create vector index: {e}")
            raise

    print("\n🎉 Database setup complete!")

if __name__ == "__main__":
    setup_database()