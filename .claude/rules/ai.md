# AI/LLM Integration Standards

## Core Principles
<principles>
1. **Mock First, Real Later**: Use mock responses until credentials available
2. **Structured Prompts**: Use templates with clear input/output formats
3. **RAG Context**: Include similar queries in prompts for consistency
4. **Error Handling**: Always handle API failures gracefully
5. **Rate Limiting**: Implement exponential backoff for retries
</principles>

## Mock LLM Analyzer (Phase 1)
<mock_analyzer>
```python
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
```
</mock_analyzer>

## Real AWS Bedrock Integration (Phase 2)
<real_bedrock>
```python
# src/services/llm.py
import boto3
import json
from typing import Dict, List, Optional
import os

def get_bedrock_client():
    """
    Initialize AWS Bedrock client.
    
    Returns:
        boto3 Bedrock Runtime client
        
    Raises:
        ValueError: If AWS credentials not configured
    """
    region = os.getenv("AWS_REGION", "us-east-1")
    
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        raise ValueError("AWS_ACCESS_KEY_ID not set in environment")
    
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=region
    )

async def real_analyze_with_claude(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: List[Dict] = None,
    max_retries: int = 3
) -> List[Dict]:
    """
    Analyze query using Claude 3.5 Sonnet via AWS Bedrock.
    
    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN ANALYZE output
        similar_queries: Historical similar queries from RAG
        max_retries: Maximum retry attempts for API calls
        
    Returns:
        List of recommendation dictionaries
        
    Raises:
        Exception: If all retry attempts fail
    """
    client = get_bedrock_client()
    
    # Build prompt with context
    prompt = build_analysis_prompt(
        query_text=query_text,
        execution_plan=execution_plan,
        similar_queries=similar_queries
    )
    
    # Prepare request body
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "temperature": 0.3,  # Lower temp for more consistent recommendations
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    })
    
    # Call Bedrock with exponential backoff
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
                body=body
            )
            
            # Parse response
            response_body = json.loads(response["body"].read())
            recommendations_text = response_body["content"][0]["text"]
            
            # Parse recommendations from Claude's response
            recommendations = parse_recommendations(recommendations_text)
            
            return recommendations
            
        except client.exceptions.ThrottlingException:
            # Exponential backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)
            else:
                raise
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1)
    
    raise Exception("Failed to analyze query after all retries")
```
</real_bedrock>

## Prompt Template
<prompt_template>
```python
def build_analysis_prompt(
    query_text: str,
    execution_plan: Optional[Dict] = None,
    similar_queries: List[Dict] = None
) -> str:
    """
    Build structured prompt for Claude query analysis.
    
    Uses RAG context when available to ground recommendations.
    
    Args:
        query_text: SQL query to analyze
        execution_plan: Optional EXPLAIN output
        similar_queries: Historical similar queries
        
    Returns:
        Formatted prompt string
    """
    prompt_parts = []
    
    # System context
    prompt_parts.append("""You are a PostgreSQL query optimization expert.
Your task is to analyze slow queries and provide actionable recommendations.

Return your analysis as JSON in this exact format:
{
  "recommendations": [
    {
      "type": "add_index | rewrite | schema",
      "description": "Human-readable explanation",
      "sql": "SQL to apply recommendation or null",
      "predicted_improvement": "percentage as string like '60%'"
    }
  ]
}
""")
    
    # Query being analyzed
    prompt_parts.append(f"\n<query_to_analyze>\n{query_text}\n</query_to_analyze>")
    
    # Execution plan if available
    if execution_plan:
        prompt_parts.append(f"\n<execution_plan>\n{json.dumps(execution_plan, indent=2)}\n</execution_plan>")
    
    # RAG context - similar queries
    if similar_queries and len(similar_queries) > 0:
        prompt_parts.append("\n<similar_historical_queries>")
        for sq in similar_queries[:3]:  # Top 3 only
            prompt_parts.append(f"""
Query: {sq.get('query_text', 'N/A')}
Similarity: {sq.get('similarity_score', 0):.2f}
Previous optimization: {sq.get('optimization_applied', 'None')}
---
""")
        prompt_parts.append("</similar_historical_queries>")
        
        prompt_parts.append("""
Based on these similar queries, consider recommending similar optimizations
if the patterns match. This improves consistency across the system.
""")
    
    # Instructions
    prompt_parts.append("""
Analyze the query and provide 1-3 specific, actionable recommendations.
Focus on:
1. Missing indexes (most common win)
2. Query rewrites (subqueries, JOINs, WHERE clauses)
3. Schema improvements (data types, normalization)

Be specific. If recommending an index, provide the exact CREATE INDEX statement.
If recommending a rewrite, show the improved query.

Return ONLY the JSON, no markdown formatting.
""")
    
    return "\n".join(prompt_parts)
```
</prompt_template>

## Response Parsing
<response_parsing>
```python
import json
import re

def parse_recommendations(llm_response: str) -> List[Dict]:
    """
    Parse Claude's response into structured recommendations.
    
    Handles variations in JSON formatting from LLM.
    
    Args:
        llm_response: Raw text response from Claude
        
    Returns:
        List of recommendation dictionaries
        
    Raises:
        ValueError: If response cannot be parsed
    """
    # Try to extract JSON from response
    # Sometimes LLM adds markdown formatting
    json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
    
    if not json_match:
        raise ValueError("No JSON found in LLM response")
    
    try:
        data = json.loads(json_match.group(0))
        recommendations = data.get("recommendations", [])
        
        # Validate structure
        for rec in recommendations:
            if "type" not in rec or "description" not in rec:
                raise ValueError("Invalid recommendation structure")
            
            # Ensure predicted_improvement is a string
            if "predicted_improvement" in rec:
                if not isinstance(rec["predicted_improvement"], str):
                    rec["predicted_improvement"] = f"{rec['predicted_improvement']}%"
        
        return recommendations
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}")
```
</response_parsing>

## Error Handling & Retry Logic
<error_handling>
```python
import asyncio
from typing import Callable, Any

async def retry_with_exponential_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    *args,
    **kwargs
) -> Any:
    """
    Retry function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        *args, **kwargs: Arguments to pass to func
        
    Returns:
        Function result if successful
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                print(f"Attempt {attempt + 1} failed, retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"All {max_retries} attempts failed")
    
    raise last_exception
```
</error_handling>

## Rate Limit Handling
<rate_limiting>
For AWS Bedrock, implement these strategies:

1. **Exponential Backoff** (implemented above)
2. **Request Queue** (Phase 2 with Celery)
3. **Circuit Breaker** (stop requests after N failures)

```python
class CircuitBreaker:
    """Simple circuit breaker for API calls."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        """Call function through circuit breaker."""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
    
    def on_success(self):
        """Reset on successful call."""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def on_failure(self):
        """Track failures and open circuit if needed."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
```
</rate_limiting>

## Testing LLM Integration
<testing>
```python
# tests/test_llm.py
import pytest
from src.services.llm import mock_analyze_with_claude, build_analysis_prompt

@pytest.mark.asyncio
async def test_mock_analyzer_returns_recommendations():
    """Test mock analyzer returns valid recommendations."""
    recs = await mock_analyze_with_claude(
        query_text="SELECT * FROM users WHERE email LIKE '%gmail%'"
    )
    
    assert len(recs) > 0
    assert "type" in recs[0]
    assert "description" in recs[0]
    assert "predicted_improvement" in recs[0]

@pytest.mark.asyncio
async def test_mock_analyzer_detects_like_pattern():
    """Test mock analyzer detects LIKE wildcard pattern."""
    recs = await mock_analyze_with_claude(
        query_text="SELECT * FROM users WHERE email LIKE '%@gmail.com'"
    )
    
    # Should recommend index for LIKE pattern
    assert any("index" in rec["type"] for rec in recs)

def test_prompt_includes_rag_context():
    """Test prompt builder includes similar queries."""
    similar = [
        {
            "query_text": "SELECT * FROM orders",
            "similarity_score": 0.85,
            "optimization_applied": "Added index on user_id"
        }
    ]
    
    prompt = build_analysis_prompt(
        query_text="SELECT * FROM orders WHERE user_id = 1",
        similar_queries=similar
    )
    
    assert "similar_historical_queries" in prompt
    assert "0.85" in prompt
    assert "Added index" in prompt
```
</testing>

## Migration Path: Mock → Real
<migration>
When AWS credentials become available:

1. **Update .env**
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
```

2. **Update service imports**
```python
# src/services/analyzer.py

# Phase 1 (MVP)
from src.services.llm import mock_analyze_with_claude as analyze_with_claude

# Phase 2 (Production) - just change the import
from src.services.llm import real_analyze_with_claude as analyze_with_claude
```

3. **Test with real API**
```bash
python -c "
from src.services.llm import real_analyze_with_claude
import asyncio

async def test():
    recs = await real_analyze_with_claude('SELECT * FROM users')
    print(recs)

asyncio.run(test())
"
```
</migration>

## AI Integration Checklist
<checklist>
- Mock LLM responses for MVP (no blocked progress)
- Structured prompt template with RAG context
- JSON output format specified in prompt
- Response parsing handles LLM variations
- Exponential backoff for retries
- Circuit breaker for repeated failures
- Error messages logged with context
- Timeout set for API calls (30s)
- Rate limit handling implemented
- Easy migration path from mock to real
</checklist>

## Anti-Patterns to Avoid
<anti_patterns>
- DON'T block MVP waiting for AWS credentials
- DON'T use unstructured prompts (specify JSON format)
- DON'T skip RAG context in prompts
- DON'T trust LLM output without validation
- DON'T retry indefinitely without backoff
- DON'T expose API keys in code or logs
- DON'T skip error handling on API calls
- DON'T use high temperature for optimization tasks
- DON'T ignore rate limits
- DON'T parse LLM responses with brittle regex
</anti_patterns>
