# src/api/routes/analysis.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.core.database import get_db
from src.api.models import AnalyzeRequest, AnalyzeResponse
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
        print(f"Error analyzing query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze query"
        )

@router.get(
    "/analysis/{analysis_id}",
    response_model=AnalyzeResponse,
    summary="Get analysis results",
    description="Retrieve analysis results by analysis ID"
)
async def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db)
) -> AnalyzeResponse:
    """
    Retrieve analysis results by ID.

    Args:
        analysis_id: Analysis identifier
        db: Database session (injected)

    Returns:
        AnalyzeResponse with recommendations and similar queries

    Raises:
        HTTPException: 404 if analysis not found, 500 if processing fails
    """
    try:
        # For MVP, we'll return a placeholder response
        # In Phase 2, implement proper analysis retrieval from database
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis retrieval not implemented in MVP"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis"
        )