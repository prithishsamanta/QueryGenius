# src/api/models.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

class AnalyzeRequest(BaseModel):
    """Request model for query analysis."""

    query_text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="SQL query to analyze"
    )
    execution_time_ms: float = Field(
        ...,
        gt=0,
        description="Query execution time in milliseconds"
    )
    execution_plan: Optional[dict] = Field(
        None,
        description="EXPLAIN ANALYZE output as JSON"
    )
    schema_context: Optional[List[dict]] = Field(
        None,
        description=(
            "Schema info for tables referenced in the query. "
            "Each entry should have: table (str), columns (list of {name, type, nullable}), "
            "indexes (list of {name, columns, unique}). "
            "Generate this via fetch_schema_from_db() in src/utils/parsers.py."
        )
    )

    @validator("query_text")
    def validate_query_text(cls, v):
        if not v.strip():
            raise ValueError("Query text cannot be empty")
        if "DROP TABLE" in v.upper() or "DELETE FROM" in v.upper():
            raise ValueError("Destructive queries not allowed")
        return v.strip()

class Recommendation(BaseModel):
    """Single optimization recommendation."""

    type: str = Field(..., description="Recommendation type: add_index, rewrite, schema")
    description: str = Field(..., description="Human-readable recommendation")
    sql: Optional[str] = Field(None, description="SQL to apply recommendation")
    predicted_improvement: str = Field(..., description="Expected improvement percentage")

class SimilarQuery(BaseModel):
    """Historical similar query."""

    query_id: int
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    optimization_applied: Optional[str] = None

class AnalyzeResponse(BaseModel):
    """Response model for query analysis."""

    analysis_id: str
    status: str = Field(..., description="completed | failed | processing")
    recommendations: List[Recommendation]
    similar_queries: List[SimilarQuery]
    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "recommendations": [
                    {
                        "type": "add_index",
                        "description": "Add index on users.email",
                        "sql": "CREATE INDEX idx_users_email ON users(email);",
                        "predicted_improvement": "60%"
                    }
                ],
                "similar_queries": [
                    {
                        "query_id": 42,
                        "similarity_score": 0.87,
                        "optimization_applied": "Added email index"
                    }
                ],
                "created_at": "2025-11-15T10:30:00Z"
            }
        }