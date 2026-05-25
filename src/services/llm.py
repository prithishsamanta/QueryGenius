# src/services/llm.py
from typing import Dict, List, Optional

from src.utils.parsers import format_schema_for_prompt


def build_analysis_prompt(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: Optional[List[Dict]] = None,
    schema_context: Optional[List[Dict]] = None,
) -> str:
    """
    Build a structured prompt for Claude query analysis.

    Injects schema context (table definitions, existing indexes) and RAG
    context (similar historical queries) so recommendations reference actual
    column names and avoid suggesting indexes that already exist.

    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN ANALYZE output as a dict
        similar_queries: Historical similar queries from pgvector search
        schema_context: Table schema dicts from fetch_schema_from_db()

    Returns:
        Formatted prompt string ready to send to Claude

    Example:
        >>> prompt = build_analysis_prompt(
        ...     query_text="SELECT * FROM users WHERE email LIKE '%gmail%'",
        ...     schema_context=[{"table": "users", "columns": [...], "indexes": [...]}]
        ... )
        >>> "<schema>" in prompt
        True
    """
    import json

    parts = []

    parts.append(
        "You are a PostgreSQL query optimization expert.\n"
        "Analyze the slow query below and provide actionable recommendations.\n"
        "Return your analysis as JSON in this exact format:\n"
        "{\n"
        '  "recommendations": [\n'
        "    {\n"
        '      "type": "add_index | rewrite | schema",\n'
        '      "description": "Human-readable explanation",\n'
        '      "sql": "SQL to apply recommendation or null",\n'
        '      "predicted_improvement": "percentage as string like \'60%\'"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    # Schema context — gives Claude actual column names and existing indexes
    if schema_context:
        formatted = format_schema_for_prompt(schema_context)
        parts.append(f"\n<schema>\n{formatted}\n</schema>")
    else:
        parts.append(
            "\n<schema>\nNo schema provided. "
            "Infer table structure from the query text.\n</schema>"
        )

    # The query being analyzed
    parts.append(f"\n<query>\n{query_text}\n</query>")

    # Execution plan if available
    if execution_plan:
        parts.append(
            f"\n<execution_plan>\n{json.dumps(execution_plan, indent=2)}\n</execution_plan>"
        )

    # RAG context — similar historical queries
    if similar_queries:
        parts.append("\n<similar_historical_queries>")
        for sq in similar_queries[:3]:
            parts.append(
                f"Query: {sq.get('query_text', 'N/A')}\n"
                f"Similarity: {sq.get('similarity_score', 0):.2f}\n"
                f"Execution time: {sq.get('execution_time_ms', 'N/A')}ms\n"
                "---"
            )
        parts.append(
            "</similar_historical_queries>\n"
            "Consider similar optimizations if the patterns match."
        )

    parts.append(
        "\nProvide 1-3 specific, actionable recommendations. "
        "If schema is provided, use exact column names in your SQL. "
        "Do not recommend indexes that already exist in the schema. "
        "Return ONLY the JSON, no markdown formatting."
    )

    return "\n".join(parts)


async def mock_analyze_with_claude(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: Optional[List[Dict]] = None,
    schema_context: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    Mock Claude analysis for MVP development.

    Returns realistic recommendations without calling AWS Bedrock.
    Uses schema_context when available to produce precise recommendations
    with actual column names and index-aware suggestions.
    Replace this with real_analyze_with_claude() in Phase 2.

    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN ANALYZE output
        similar_queries: Historical similar queries from RAG
        schema_context: Table schema dicts from fetch_schema_from_db()

    Returns:
        List of recommendation dictionaries

    Example:
        >>> recs = await mock_analyze_with_claude(
        ...     "SELECT * FROM users WHERE email LIKE '%gmail%'",
        ...     schema_context=[{"table": "users", "columns": [{"name": "email", "type": "text"}], "indexes": []}]
        ... )
        >>> recs[0]['type']
        'add_index'
    """
    # Build the prompt — this is what will be sent to real Bedrock in Phase 2
    prompt = build_analysis_prompt(
        query_text=query_text,
        execution_plan=execution_plan,
        similar_queries=similar_queries,
        schema_context=schema_context,
    )

    recommendations = []

    # Derive existing index column names from schema to avoid duplicates
    existing_indexed_cols: set = set()
    if schema_context:
        for table in schema_context:
            for idx in table.get("indexes", []):
                for col in idx.get("columns", []):
                    existing_indexed_cols.add(col.lower())

    # Helper to find actual column name from schema for a given table
    def get_columns_for_table(table_name: str) -> List[str]:
        if not schema_context:
            return []
        for table in schema_context:
            if table["table"].lower() == table_name.lower():
                return [c["name"] for c in table.get("columns", [])]
        return []

    # Pattern 1: LIKE with leading wildcard
    if "LIKE" in query_text.upper() and "'%" in query_text:
        # Try to identify the table and column from schema
        affected_table = None
        affected_col = None
        if schema_context:
            for table in schema_context:
                t_name = table["table"]
                if t_name.lower() in query_text.lower():
                    affected_table = t_name
                    for col in table["columns"]:
                        if col["name"].lower() in query_text.lower() and col["type"] in ("text", "character varying"):
                            affected_col = col["name"]
                            break
                    break

        if affected_table and affected_col and affected_col.lower() not in existing_indexed_cols:
            sql = (
                f"CREATE INDEX idx_{affected_table}_{affected_col}_trgm "
                f"ON {affected_table} USING gin({affected_col} gin_trgm_ops);"
            )
        elif affected_table and affected_col:
            sql = f"-- Index on {affected_table}.{affected_col} already exists"
        else:
            sql = "CREATE INDEX idx_col_trgm ON <table> USING gin(<column> gin_trgm_ops);"

        recommendations.append({
            "type": "add_index",
            "description": (
                f"Add GIN trigram index for LIKE pattern matching"
                + (f" on {affected_table}.{affected_col}" if affected_table and affected_col else "")
            ),
            "sql": sql,
            "predicted_improvement": "65%",
        })

    # Pattern 2: Missing WHERE clause — full table scan
    if "WHERE" not in query_text.upper():
        recommendations.append({
            "type": "rewrite",
            "description": "Query has no WHERE clause — results in a full table scan",
            "sql": None,
            "predicted_improvement": "80%",
        })

    # Pattern 3: SELECT *
    if "SELECT *" in query_text.upper():
        # Suggest specific columns if schema is available
        affected_table = None
        if schema_context:
            for table in schema_context:
                if table["table"].lower() in query_text.lower():
                    affected_table = table
                    break

        if affected_table:
            cols = ", ".join(c["name"] for c in affected_table["columns"][:6])
            sql = f"SELECT {cols} FROM {affected_table['table']} ..."
        else:
            sql = None

        recommendations.append({
            "type": "rewrite",
            "description": "Replace SELECT * with specific column names to reduce I/O",
            "sql": sql,
            "predicted_improvement": "25%",
        })

    # Pattern 4: JOIN — suggest index on join column if not already indexed
    if "JOIN" in query_text.upper():
        join_sql = None
        if schema_context:
            for table in schema_context:
                t_name = table["table"]
                if t_name.lower() in query_text.lower():
                    for col in table["columns"]:
                        if col["name"].lower() in ("id", "user_id", "seat_id", "order_id", "movie_id"):
                            if col["name"].lower() not in existing_indexed_cols:
                                join_sql = (
                                    f"CREATE INDEX idx_{t_name}_{col['name']} "
                                    f"ON {t_name}({col['name']});"
                                )
                                break
                if join_sql:
                    break

        recommendations.append({
            "type": "add_index",
            "description": "Add index on JOIN column to avoid nested loop scans",
            "sql": join_sql or "-- Review execution plan to identify exact JOIN columns",
            "predicted_improvement": "50%",
        })

    # Pattern 5: Historical match from RAG
    if similar_queries:
        top = similar_queries[0]
        recommendations.append({
            "type": "historical_pattern",
            "description": (
                f"A similar query (similarity: {top['similarity_score']}) "
                f"was previously analyzed. Review its optimization."
            ),
            "sql": "-- See historical analysis for similar query",
            "predicted_improvement": "40%",
        })

    # Default fallback
    if not recommendations:
        recommendations.append({
            "type": "analysis",
            "description": "Run EXPLAIN ANALYZE to identify sequential scans and missing indexes",
            "sql": f"EXPLAIN ANALYZE {query_text}",
            "predicted_improvement": "30%",
        })

    return recommendations
