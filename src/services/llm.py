# src/services/llm.py
from typing import Dict, List, Optional
import random

async def mock_analyze_with_claude(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: List[Dict] = None
) -> List[Dict]:
    """
    Mock Claude analysis for MVP development.

    Returns realistic recommendations without calling AWS Bedrock.
    Replace this with real_analyze_with_claude() in Phase 2.

    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN output
        similar_queries: Historical similar queries from RAG

    Returns:
        List of recommendation dictionaries

    Example:
        >>> recs = await mock_analyze_with_claude("SELECT * FROM users WHERE email LIKE '%gmail%'")
        >>> recs[0]['type']
        'add_index'
    """
    # Simulate realistic recommendations based on query patterns
    recommendations = []

    # Pattern 1: LIKE with leading wildcard
    if "LIKE" in query_text.upper() and "'%" in query_text:
        recommendations.append({
            "type": "add_index",
            "description": "Add trigram or full-text index for LIKE pattern matching",
            "sql": "CREATE INDEX idx_email_pattern ON users USING gin(email gin_trgm_ops);",
            "predicted_improvement": "65%"
        })

    # Pattern 2: Missing WHERE clause
    if "WHERE" not in query_text.upper():
        recommendations.append({
            "type": "rewrite",
            "description": "Add WHERE clause to limit result set",
            "sql": None,
            "predicted_improvement": "80%"
        })

    # Pattern 3: SELECT *
    if "SELECT *" in query_text.upper():
        recommendations.append({
            "type": "rewrite",
            "description": "Select specific columns instead of SELECT *",
            "sql": None,
            "predicted_improvement": "25%"
        })

    # Pattern 4: JOIN without index
    if "JOIN" in query_text.upper():
        recommendations.append({
            "type": "add_index",
            "description": "Add index on JOIN columns for better performance",
            "sql": "-- Analyze execution plan to determine exact columns",
            "predicted_improvement": "50%"
        })

    # If we found similar queries, add a recommendation based on that
    if similar_queries and len(similar_queries) > 0:
        top_similar = similar_queries[0]
        recommendations.append({
            "type": "historical_pattern",
            "description": f"Similar query (score: {top_similar['similarity_score']}) was optimized before",
            "sql": "-- Review historical optimization from similar query",
            "predicted_improvement": "40%"
        })

    # Default recommendation if none matched
    if not recommendations:
        recommendations.append({
            "type": "analysis",
            "description": "Review execution plan for sequential scans and missing indexes",
            "sql": "EXPLAIN ANALYZE " + query_text,
            "predicted_improvement": "30%"
        })

    return recommendations