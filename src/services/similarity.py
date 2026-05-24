# src/services/similarity.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict
import numpy as np

from src.models.schemas import Query

def find_similar_queries(
    db: Session,
    query_embedding: List[float],
    top_k: int = 5,
    similarity_threshold: float = 0.7
) -> List[Dict]:
    """
    Find similar queries using pgvector cosine similarity.

    Args:
        db: Database session
        query_embedding: Vector embedding to search for (384-dim)
        top_k: Number of similar queries to return
        similarity_threshold: Minimum similarity score (0.0-1.0)

    Returns:
        List of similar queries with metadata

    Example:
        >>> embedding = generate_embedding("SELECT * FROM users")
        >>> similar = find_similar_queries(db, embedding, top_k=3)
        >>> similar[0]['similarity_score']
        0.87
    """
    # For MVP, if no existing queries, return empty list
    query_count = db.query(Query).count()
    if query_count == 0:
        return []

    # Convert embedding to string format for SQL
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Use raw SQL with proper parameter substitution for pgvector
    sql = f"""
        SELECT
            id,
            query_text,
            execution_time_ms,
            1 - (embedding <-> '{embedding_str}'::vector) AS similarity_score
        FROM queries
        WHERE 1 - (embedding <-> '{embedding_str}'::vector) >= {similarity_threshold}
        ORDER BY embedding <-> '{embedding_str}'::vector
        LIMIT {top_k}
    """

    result = db.execute(text(sql))

    similar_queries = []
    for row in result:
        similar_queries.append({
            "query_id": row.id,
            "query_text": row.query_text,
            "execution_time_ms": row.execution_time_ms,
            "similarity_score": round(float(row.similarity_score), 3)
        })

    return similar_queries