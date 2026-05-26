#!/usr/bin/env python3
"""
Seed the QueryGenius database with 10,000 sample slow queries.

Generates realistic SQL query patterns across common slow-query categories,
encodes them in batches using sentence-transformers, and bulk-inserts them
into the queries table. After insertion, rebuilds the IVFFlat index so that
cluster centroids are computed on real data rather than an empty table.

Run this script once after setup_db.py:
    python scripts/seed_data.py
"""
import sys
import os
import random
import time
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from src.core.embeddings import get_embedding_model
from src.models.schemas import Query, Optimization

load_dotenv()

# Batch sizes
EMBEDDING_BATCH_SIZE = 256  # Encode this many queries at once
INSERT_BATCH_SIZE = 500      # Insert this many rows per DB transaction
TOTAL_QUERIES = 10_000


# ---------------------------------------------------------------------------
# Query template library
# Each entry is a (template_string, execution_time_range_ms, databases) tuple.
# Templates use .format() placeholders filled with random values at generation time.
# ---------------------------------------------------------------------------

TABLES = [
    "users", "orders", "products", "bookings", "seats",
    "movies", "payments", "sessions", "reviews", "inventory",
    "employees", "departments", "tickets", "events", "venues",
    "customers", "shipments", "invoices", "subscriptions", "logs",
]

COLUMNS = {
    "users":         ["id", "email", "name", "created_at", "status", "role", "last_login"],
    "orders":        ["id", "user_id", "total", "status", "created_at", "updated_at"],
    "products":      ["id", "name", "price", "category", "stock", "created_at"],
    "bookings":      ["id", "user_id", "seat_id", "status", "created_at", "movie_id"],
    "seats":         ["id", "movie_id", "row", "number", "status"],
    "movies":        ["id", "title", "genre", "release_date", "rating"],
    "payments":      ["id", "order_id", "amount", "method", "status", "created_at"],
    "sessions":      ["id", "user_id", "token", "created_at", "expires_at"],
    "reviews":       ["id", "product_id", "user_id", "rating", "created_at"],
    "inventory":     ["id", "product_id", "quantity", "warehouse_id", "updated_at"],
    "employees":     ["id", "department_id", "name", "salary", "hired_at"],
    "departments":   ["id", "name", "manager_id", "budget"],
    "tickets":       ["id", "event_id", "user_id", "price", "status", "created_at"],
    "events":        ["id", "venue_id", "name", "start_at", "capacity"],
    "venues":        ["id", "name", "city", "capacity"],
    "customers":     ["id", "email", "name", "tier", "created_at"],
    "shipments":     ["id", "order_id", "status", "shipped_at", "delivered_at"],
    "invoices":      ["id", "customer_id", "total", "due_date", "paid_at"],
    "subscriptions": ["id", "user_id", "plan", "status", "renews_at"],
    "logs":          ["id", "user_id", "action", "created_at", "ip_address"],
}

STATUSES      = ["active", "inactive", "pending", "confirmed", "cancelled", "completed", "failed"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com", "company.com", "example.com"]
GENRES        = ["action", "comedy", "drama", "thriller", "horror", "romance"]
PLANS         = ["free", "basic", "pro", "enterprise"]
TIERS         = ["bronze", "silver", "gold", "platinum"]


def _table_col(table: str) -> str:
    """Return a random column name for the given table."""
    return random.choice(COLUMNS.get(table, ["id", "created_at", "status"]))


def _random_table() -> str:
    return random.choice(TABLES)


def _random_int(lo: int = 1, hi: int = 10000) -> int:
    return random.randint(lo, hi)


def _random_domain() -> str:
    return random.choice(EMAIL_DOMAINS)


def _random_status() -> str:
    return random.choice(STATUSES)


def generate_query_templates() -> List[Dict]:
    """
    Generate a diverse library of slow query templates.

    Returns:
        List of dicts with keys: query_text, execution_time_ms, database_name
    """
    templates = []

    t1 = _random_table()
    t2 = _random_table()
    while t2 == t1:
        t2 = _random_table()

    # --- Pattern 1: SELECT * with no WHERE (full table scan) ---
    for _ in range(800):
        t = _random_table()
        templates.append({
            "query_text": f"SELECT * FROM {t}",
            "execution_time_ms": round(random.uniform(800, 4000), 2),
            "database_name": "production",
        })

    # --- Pattern 2: LIKE with leading wildcard (no index use) ---
    for _ in range(800):
        t = _random_table()
        col = _table_col(t)
        domain = _random_domain()
        templates.append({
            "query_text": f"SELECT * FROM {t} WHERE {col} LIKE '%{domain}'",
            "execution_time_ms": round(random.uniform(1200, 5000), 2),
            "database_name": "production",
        })

    # --- Pattern 3: JOIN without index on join column ---
    for _ in range(1000):
        t1 = _random_table()
        t2 = _random_table()
        while t2 == t1:
            t2 = _random_table()
        col1 = _table_col(t1)
        col2 = _table_col(t2)
        status = _random_status()
        templates.append({
            "query_text": (
                f"SELECT {t1}.*, {t2}.{col2} FROM {t1} "
                f"JOIN {t2} ON {t1}.id = {t2}.{col1} "
                f"WHERE {t1}.status = '{status}'"
            ),
            "execution_time_ms": round(random.uniform(1500, 6000), 2),
            "database_name": "production",
        })

    # --- Pattern 4: COUNT(*) without index ---
    for _ in range(600):
        t = _random_table()
        col = _table_col(t)
        status = _random_status()
        templates.append({
            "query_text": f"SELECT COUNT(*) FROM {t} WHERE {col} = '{status}'",
            "execution_time_ms": round(random.uniform(900, 3500), 2),
            "database_name": "production",
        })

    # --- Pattern 5: ORDER BY on non-indexed column ---
    for _ in range(700):
        t = _random_table()
        col = _table_col(t)
        templates.append({
            "query_text": f"SELECT * FROM {t} ORDER BY {col} DESC LIMIT 100",
            "execution_time_ms": round(random.uniform(700, 3000), 2),
            "database_name": "production",
        })

    # --- Pattern 6: Subquery instead of JOIN ---
    for _ in range(700):
        t1 = _random_table()
        t2 = _random_table()
        while t2 == t1:
            t2 = _random_table()
        col = _table_col(t2)
        templates.append({
            "query_text": (
                f"SELECT * FROM {t1} "
                f"WHERE id IN (SELECT {col} FROM {t2} WHERE status = 'active')"
            ),
            "execution_time_ms": round(random.uniform(2000, 8000), 2),
            "database_name": "production",
        })

    # --- Pattern 7: GROUP BY without index ---
    for _ in range(600):
        t = _random_table()
        col = _table_col(t)
        templates.append({
            "query_text": (
                f"SELECT {col}, COUNT(*) as total FROM {t} "
                f"GROUP BY {col} ORDER BY total DESC"
            ),
            "execution_time_ms": round(random.uniform(1000, 4500), 2),
            "database_name": "production",
        })

    # --- Pattern 8: Date range scan without index ---
    for _ in range(700):
        t = _random_table()
        days = _random_int(7, 90)
        templates.append({
            "query_text": (
                f"SELECT * FROM {t} "
                f"WHERE created_at >= NOW() - INTERVAL '{days} days'"
            ),
            "execution_time_ms": round(random.uniform(800, 3500), 2),
            "database_name": "production",
        })

    # --- Pattern 9: Multiple JOINs (N+1 style) ---
    for _ in range(800):
        t1 = _random_table()
        t2 = _random_table()
        t3 = _random_table()
        while t2 == t1:
            t2 = _random_table()
        while t3 == t1 or t3 == t2:
            t3 = _random_table()
        templates.append({
            "query_text": (
                f"SELECT {t1}.*, {t2}.id as {t2}_id, {t3}.status as {t3}_status "
                f"FROM {t1} "
                f"JOIN {t2} ON {t1}.id = {t2}.id "
                f"JOIN {t3} ON {t2}.id = {t3}.id "
                f"WHERE {t1}.status = 'active'"
            ),
            "execution_time_ms": round(random.uniform(2500, 9000), 2),
            "database_name": "production",
        })

    # --- Pattern 10: DISTINCT on large table ---
    for _ in range(500):
        t = _random_table()
        col = _table_col(t)
        templates.append({
            "query_text": f"SELECT DISTINCT {col} FROM {t}",
            "execution_time_ms": round(random.uniform(600, 2500), 2),
            "database_name": "production",
        })

    # --- Pattern 11: NOT IN subquery (very slow) ---
    for _ in range(500):
        t1 = _random_table()
        t2 = _random_table()
        while t2 == t1:
            t2 = _random_table()
        templates.append({
            "query_text": (
                f"SELECT * FROM {t1} "
                f"WHERE id NOT IN (SELECT id FROM {t2} WHERE status = 'active')"
            ),
            "execution_time_ms": round(random.uniform(3000, 12000), 2),
            "database_name": "production",
        })

    # --- Pattern 12: Function on indexed column (defeats index) ---
    for _ in range(500):
        t = _random_table()
        col = _table_col(t)
        templates.append({
            "query_text": (
                f"SELECT * FROM {t} "
                f"WHERE LOWER({col}) = 'active'"
            ),
            "execution_time_ms": round(random.uniform(900, 4000), 2),
            "database_name": "production",
        })

    # --- Pattern 13: HAVING without GROUP index ---
    for _ in range(400):
        t = _random_table()
        col = _table_col(t)
        threshold = _random_int(5, 100)
        templates.append({
            "query_text": (
                f"SELECT {col}, COUNT(*) as cnt FROM {t} "
                f"GROUP BY {col} HAVING COUNT(*) > {threshold}"
            ),
            "execution_time_ms": round(random.uniform(1200, 5000), 2),
            "database_name": "production",
        })

    # --- Pattern 14: OR condition preventing index use ---
    for _ in range(400):
        t = _random_table()
        col1 = _table_col(t)
        col2 = _table_col(t)
        s1 = _random_status()
        s2 = _random_status()
        templates.append({
            "query_text": (
                f"SELECT * FROM {t} "
                f"WHERE {col1} = '{s1}' OR {col2} = '{s2}'"
            ),
            "execution_time_ms": round(random.uniform(700, 3000), 2),
            "database_name": "production",
        })

    # --- Pattern 15: Wildcard LIKE both sides ---
    for _ in range(500):
        t = _random_table()
        col = _table_col(t)
        keyword = random.choice(["active", "pending", "user", "order", "payment"])
        templates.append({
            "query_text": f"SELECT * FROM {t} WHERE {col} LIKE '%{keyword}%'",
            "execution_time_ms": round(random.uniform(1500, 6000), 2),
            "database_name": "production",
        })

    return templates


def build_query_pool(target: int) -> List[Dict]:
    """
    Build a pool of query dicts of exactly `target` size by cycling through
    generated templates with slight variation to ensure uniqueness.

    Args:
        target: Number of queries to generate

    Returns:
        List of query dicts
    """
    base = generate_query_templates()
    pool = []

    while len(pool) < target:
        for entry in base:
            if len(pool) >= target:
                break
            # Add slight variation so embeddings are not identical
            variant = dict(entry)
            variant["execution_time_ms"] = round(
                entry["execution_time_ms"] * random.uniform(0.8, 1.3), 2
            )
            # Vary created_at timestamp across the past 6 months
            days_ago = random.randint(0, 180)
            seconds_ago = random.randint(0, 86400)
            variant["created_at"] = datetime.utcnow() - timedelta(
                days=days_ago, seconds=seconds_ago
            )
            pool.append(variant)

    return pool[:target]


def seed(total: int = TOTAL_QUERIES) -> None:
    """
    Seed the database with `total` sample queries.

    Steps:
        1. Generate query text pool
        2. Batch-encode all query texts into embeddings
        3. Bulk-insert in chunks
        4. Rebuild IVFFlat index on real data

    Args:
        total: Number of queries to insert (default 10,000)
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)

    print(f"Generating {total:,} query records...")
    pool = build_query_pool(total)
    query_texts = [q["query_text"] for q in pool]

    print(f"Loading embedding model...")
    model = get_embedding_model()

    print(f"Encoding {total:,} queries in batches of {EMBEDDING_BATCH_SIZE}...")
    start = time.time()
    embeddings = model.encode(
        query_texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    elapsed = round(time.time() - start, 1)
    print(f"Encoding complete in {elapsed}s")

    print(f"Inserting into database in batches of {INSERT_BATCH_SIZE}...")
    db = SessionLocal()
    try:
        inserted = 0
        for batch_start in range(0, total, INSERT_BATCH_SIZE):
            batch_end = min(batch_start + INSERT_BATCH_SIZE, total)
            batch = []

            for i in range(batch_start, batch_end):
                entry = pool[i]
                batch.append(Query(
                    analysis_id=str(uuid.uuid4()),
                    query_text=entry["query_text"],
                    execution_time_ms=entry["execution_time_ms"],
                    execution_plan=None,
                    database_name=entry.get("database_name", "production"),
                    created_at=entry.get("created_at", datetime.utcnow()),
                    embedding=embeddings[i].tolist(),
                ))

            db.bulk_save_objects(batch)
            db.commit()
            inserted += len(batch)
            print(f"  Inserted {inserted:,} / {total:,} rows")

    except Exception as e:
        db.rollback()
        print(f"Insert failed: {e}")
        raise
    finally:
        db.close()

    print("\nRebuilding IVFFlat index on real data...")
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS queries_embedding_idx;"))
        conn.execute(text(
            "CREATE INDEX queries_embedding_idx "
            "ON queries USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 100);"
        ))
        conn.commit()
    print("Index rebuilt successfully")

    print(f"\nSeeding complete — {total:,} queries inserted and indexed.")


if __name__ == "__main__":
    seed()
