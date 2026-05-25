# src/api/routes/analysis.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.core.database import get_db
from src.api.models import AnalyzeRequest, AnalyzeResponse, Recommendation, SimilarQuery
from src.services.analyzer import AnalyzerService
from src.models.schemas import Query, Optimization

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
            execution_plan=request.execution_plan,
            schema_context=request.schema_context
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
        query = db.query(Query).filter(Query.analysis_id == analysis_id).first()

        if query is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis {analysis_id} not found"
            )

        optimizations = db.query(Optimization).filter(
            Optimization.query_id == query.id
        ).all()

        recommendations = [
            Recommendation(
                type=opt.recommendation_type,
                description=opt.recommendation_text,
                sql=None,
                predicted_improvement=f"{opt.predicted_improvement_percent}%"
            )
            for opt in optimizations
        ]

        return AnalyzeResponse(
            analysis_id=query.analysis_id,
            status="completed",
            recommendations=recommendations,
            similar_queries=[],
            created_at=query.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis"
        )