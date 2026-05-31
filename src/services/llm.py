# src/services/llm.py
import asyncio
import json
import logging
import os
import re
import time
from functools import partial
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from src.utils.parsers import format_schema_for_prompt

logger = logging.getLogger(__name__)

# Cached Bedrock client — initialized on first call
_bedrock_client = None


class CircuitBreaker:
    """
    Circuit breaker for AWS Bedrock API calls.

    Prevents repeated calls to a failing service by tracking consecutive
    failures and temporarily blocking requests once a threshold is reached.

    States:
        CLOSED — requests flow normally
        OPEN — requests are blocked (service assumed down)
        HALF_OPEN — one test request allowed to check recovery

    Args:
        failure_threshold: Number of consecutive failures before opening
        reset_timeout: Seconds to wait before transitioning OPEN to HALF_OPEN
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count: int = 0
        self.last_failure_time: Optional[float] = None
        self.state: str = "CLOSED"

    def allow_request(self) -> bool:
        """
        Check whether the circuit allows a request through.

        Returns:
            True if the request should proceed, False if blocked
        """
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.reset_timeout:
                self.state = "HALF_OPEN"
                return True
            return False

        # HALF_OPEN — allow one test request
        return True

    def record_success(self) -> None:
        """Reset failure tracking after a successful call."""
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        """Record a failure and open the circuit if threshold is reached."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                "Circuit breaker OPEN after %d consecutive failures",
                self.failure_count,
            )


# Module-level circuit breaker instance shared across all calls
_circuit_breaker = CircuitBreaker()


def get_bedrock_client():
    """
    Get or initialize the cached AWS Bedrock Runtime client.

    Uses AWS_REGION from environment (defaults to us-east-1).
    AWS credentials are read from environment variables or the default
    credential chain (instance profile, config file, etc.).

    Returns:
        boto3 Bedrock Runtime client

    Raises:
        ValueError: If AWS_ACCESS_KEY_ID is not set in environment
    """
    global _bedrock_client
    if _bedrock_client is not None:
        return _bedrock_client

    if not os.getenv("AWS_ACCESS_KEY_ID"):
        raise ValueError(
            "AWS_ACCESS_KEY_ID not set — cannot initialize Bedrock client"
        )

    region = os.getenv("AWS_REGION", "us-east-1")
    _bedrock_client = boto3.client(
        service_name="bedrock-runtime",
        region_name=region,
    )
    logger.info("Bedrock client initialized (region=%s)", region)
    return _bedrock_client


def parse_recommendations(llm_response: str) -> List[Dict]:
    """
    Parse Claude's text response into structured recommendation dicts.

    Handles variations in LLM output: raw JSON, markdown-fenced JSON,
    and extra surrounding text. Validates that each recommendation has
    the required fields.

    Args:
        llm_response: Raw text response from Claude via Bedrock

    Returns:
        List of recommendation dicts with keys: type, description,
        sql (nullable), predicted_improvement (string with %)

    Raises:
        ValueError: If no valid JSON found or structure is invalid
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```json\s*", "", llm_response)
    cleaned = re.sub(r"```\s*", "", cleaned)

    # Find the outermost JSON object
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not json_match:
        raise ValueError("No JSON object found in LLM response")

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON from LLM response: {exc}")

    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        raise ValueError("'recommendations' must be a list")

    for rec in recommendations:
        if "type" not in rec or "description" not in rec:
            raise ValueError(
                "Each recommendation must have 'type' and 'description'"
            )

        # Coerce predicted_improvement to string with % suffix
        improvement = rec.get("predicted_improvement", "0%")
        if isinstance(improvement, (int, float)):
            rec["predicted_improvement"] = f"{improvement}%"
        elif isinstance(improvement, str) and not improvement.endswith("%"):
            rec["predicted_improvement"] = f"{improvement}%"

        # Default sql to None if missing
        if "sql" not in rec:
            rec["sql"] = None

    return recommendations


async def real_analyze_with_claude(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: Optional[List[Dict]] = None,
    schema_context: Optional[List[Dict]] = None,
    max_retries: int = 3,
) -> List[Dict]:
    """
    Analyze a query using Claude 3.5 Sonnet via AWS Bedrock.

    Builds a structured prompt with schema and RAG context, calls the
    Bedrock InvokeModel API, parses the JSON response, and returns
    recommendations. Retries with exponential backoff on throttling.

    If the circuit breaker is open (repeated Bedrock failures), falls
    back to mock_analyze_with_claude automatically.

    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN ANALYZE output
        similar_queries: Historical similar queries from RAG
        schema_context: Table schema dicts from fetch_schema_from_db()
        max_retries: Maximum retry attempts on transient failures

    Returns:
        List of recommendation dicts

    Raises:
        Exception: If all retries exhausted and circuit breaker not tripped
    """
    # Circuit breaker check — fall back to mock if Bedrock is down
    if not _circuit_breaker.allow_request():
        logger.warning(
            "Circuit breaker OPEN — falling back to mock analyzer"
        )
        return await mock_analyze_with_claude(
            query_text=query_text,
            execution_plan=execution_plan,
            similar_queries=similar_queries,
            schema_context=schema_context,
        )

    client = get_bedrock_client()
    model_id = os.getenv(
        "AWS_BEDROCK_MODEL_ID",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
    )

    prompt = build_analysis_prompt(
        query_text=query_text,
        execution_plan=execution_plan,
        similar_queries=similar_queries,
        schema_context=schema_context,
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    })

    last_exception = None

    for attempt in range(max_retries):
        try:
            # Run the synchronous boto3 call in a thread executor
            # so we don't block the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(client.invoke_model, modelId=model_id, body=body),
            )

            response_body = json.loads(response["body"].read())
            llm_text = response_body["content"][0]["text"]

            recommendations = parse_recommendations(llm_text)
            _circuit_breaker.record_success()

            logger.info(
                "Bedrock returned %d recommendations", len(recommendations)
            )
            return recommendations

        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            last_exception = exc

            if error_code == "ThrottlingException" and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "Bedrock throttled (attempt %d/%d), retrying in %ds",
                    attempt + 1,
                    max_retries,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                _circuit_breaker.record_failure()
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(1)

        except Exception as exc:
            last_exception = exc
            _circuit_breaker.record_failure()
            logger.error("Bedrock call failed: %s", exc)

            if attempt == max_retries - 1:
                break
            await asyncio.sleep(1)

    raise last_exception


async def analyze_with_claude(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: Optional[List[Dict]] = None,
    schema_context: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    Dispatcher that routes to real or mock Claude analyzer.

    Uses real AWS Bedrock when AWS_ACCESS_KEY_ID is set in the
    environment. Falls back to the mock analyzer otherwise, allowing
    development and testing without AWS credentials.

    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN ANALYZE output
        similar_queries: Historical similar queries from RAG
        schema_context: Table schema dicts from fetch_schema_from_db()

    Returns:
        List of recommendation dicts
    """
    use_real = bool(os.getenv("AWS_ACCESS_KEY_ID"))

    if use_real:
        logger.info("Using real Bedrock analyzer")
        return await real_analyze_with_claude(
            query_text=query_text,
            execution_plan=execution_plan,
            similar_queries=similar_queries,
            schema_context=schema_context,
        )

    logger.info("AWS credentials not set — using mock analyzer")
    return await mock_analyze_with_claude(
        query_text=query_text,
        execution_plan=execution_plan,
        similar_queries=similar_queries,
        schema_context=schema_context,
    )


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
