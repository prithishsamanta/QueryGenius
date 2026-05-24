# Backend Development Standards - FastAPI

## Core Principles
<principles>
1. **Thin Controllers**: Routes only handle HTTP - delegate to services
2. **Type Everything**: Pydantic models for all request/response bodies
3. **Dependency Injection**: Use FastAPI's DI for database sessions, configs
4. **Async First**: Use async/await for all I/O operations
5. **Error Handling**: Always return structured error responses
</principles>

## FastAPI Route Structure
<route_structure>
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.core.database import get_db
from src.models.schemas import AnalyzeRequest, AnalyzeResponse
from src.services.analyzer import AnalyzerService

router = APIRouter(prefix="/api", tags=["analysis"])

@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze a slow query",
    description="Submit a PostgreSQL query for AI-powered optimization analysis"
)
async def analyze_query(
    request: AnalyzeRequest,
    db: Session = Depends(get_db)
) -> AnalyzeResponse:
    """
    Analyze a slow PostgreSQL query and return optimization recommendations.
    
    Args:
        request: Analysis request containing query text and metadata
        db: Database session (injected)
        
    Returns:
        AnalyzeResponse with recommendations and similar queries
        
    Raises:
        HTTPException: 400 if request invalid, 500 if processing fails
    """
    try:
        service = AnalyzerService(db)
        result = await service.analyze(
            query_text=request.query_text,
            execution_time_ms=request.execution_time_ms,
            execution_plan=request.execution_plan
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Log error here
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze query"
        )
```
</route_structure>

## Pydantic Models
<pydantic_models>
```python
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
```
</pydantic_models>

## Dependency Injection
<dependency_injection>
```python
# src/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/querygenius")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency.
    
    Yields:
        SQLAlchemy Session
        
    Usage:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```
</dependency_injection>

## Error Response Structure
<error_responses>
All errors must return this structure:

```python
{
    "detail": "Human-readable error message",
    "error_code": "VALIDATION_ERROR",  # Optional
    "timestamp": "2025-11-15T10:30:00Z",
    "path": "/api/analyze"  # Optional
}
```

Standard error codes:
- `VALIDATION_ERROR`: 400 - Invalid request data
- `NOT_FOUND`: 404 - Resource not found
- `DATABASE_ERROR`: 500 - Database operation failed
- `AI_SERVICE_ERROR`: 500 - LLM call failed
- `EMBEDDING_ERROR`: 500 - Vector embedding generation failed
</error_responses>

## Service Layer Pattern
<service_layer>
Keep business logic in services, not routes.

```python
# src/services/analyzer.py
from sqlalchemy.orm import Session
from typing import Dict, List
import uuid
from datetime import datetime

from src.models.schemas import Query, Optimization
from src.core.embeddings import generate_embedding
from src.services.similarity import find_similar_queries
from src.services.llm import mock_analyze_with_claude

class AnalyzerService:
    """Service for query analysis operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def analyze(
        self,
        query_text: str,
        execution_time_ms: float,
        execution_plan: Dict = None
    ) -> Dict:
        """
        Analyze a query and return recommendations.
        
        Args:
            query_text: SQL query to analyze
            execution_time_ms: Execution time in milliseconds
            execution_plan: Optional EXPLAIN output
            
        Returns:
            Analysis result with recommendations
        """
        # 1. Generate embedding
        embedding = generate_embedding(query_text)
        
        # 2. Store query in database
        query = Query(
            query_text=query_text,
            execution_time_ms=execution_time_ms,
            execution_plan=execution_plan,
            embedding=embedding,
            created_at=datetime.utcnow()
        )
        self.db.add(query)
        self.db.commit()
        self.db.refresh(query)
        
        # 3. Find similar historical queries
        similar = find_similar_queries(self.db, embedding, top_k=3)
        
        # 4. Get recommendations from LLM (mocked for now)
        recommendations = await mock_analyze_with_claude(
            query_text=query_text,
            execution_plan=execution_plan,
            similar_queries=similar
        )
        
        # 5. Store recommendations
        for rec in recommendations:
            opt = Optimization(
                query_id=query.id,
                recommendation_type=rec["type"],
                recommendation_text=rec["description"],
                predicted_improvement_percent=float(rec["predicted_improvement"].rstrip("%"))
            )
            self.db.add(opt)
        self.db.commit()
        
        return {
            "analysis_id": str(uuid.uuid4()),
            "status": "completed",
            "recommendations": recommendations,
            "similar_queries": similar,
            "created_at": query.created_at
        }
```
</service_layer>

## API Standards Checklist
<checklist>
- Every route has type hints for all parameters
- Every route has Pydantic models for request/response
- Every route has docstring with Args/Returns/Raises
- Every route uses dependency injection for database
- Every route handles errors with HTTPException
- Every route returns proper HTTP status codes
- Every async function uses await for I/O
- Every validation error returns 400 with detail
- Every server error returns 500 (not stack trace)
- Every route has OpenAPI summary and description
</checklist>

## Anti-Patterns to Avoid
<anti_patterns>
- DON'T put business logic in routes
- DON'T use raw SQL strings (use SQLAlchemy ORM)
- DON'T return SQLAlchemy models directly (use Pydantic)
- DON'T forget to close database sessions
- DON'T use blocking I/O in async functions
- DON'T return stack traces to users
- DON'T skip request validation
- DON'T hardcode URLs or credentials
</anti_patterns>
