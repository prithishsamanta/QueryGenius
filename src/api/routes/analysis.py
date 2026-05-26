# src/api/routes/analysis.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.api.models import AnalyzeRequest, AnalyzeResponse, Recommendation, SimilarQuery
from src.services.analyzer import AnalyzerService
from src.models.schemas import Query, Optimization

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a slow query for analysis",
    description=(
        "Enqueues a PostgreSQL query for async AI-powered optimization analysis. "
        "Returns immediately with status='processing'. "
        "Poll GET /api/analysis/{id} to retrieve results."
    ),
)
async def analyze_query(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """
    Submit a slow PostgreSQL query for async analysis.

    Creates a query record, enqueues the analysis task, and returns
    immediately with status='processing'. The Celery worker processes
    the task in the background.

    Args:
        request: Analysis request containing query text and metadata
        db: Database session (injected)

    Returns:
        AnalyzeResponse with status='processing' and an analysis_id to poll

    Raises:
        HTTPException: 400 if request invalid, 500 if enqueue fails
    """
    try:
        service = AnalyzerService(db)
        result = service.submit(
            query_text=request.query_text,
            execution_time_ms=request.execution_time_ms,
            execution_plan=request.execution_plan,
            schema_context=request.schema_context,
        )
        return AnalyzeResponse(
            analysis_id=result["analysis_id"],
            status=result["status"],
            recommendations=[],
            similar_queries=[],
            created_at=result["created_at"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        print(f"Error submitting analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit query for analysis",
        )


@router.get(
    "/analysis/{analysis_id}",
    response_model=AnalyzeResponse,
    summary="Get analysis results",
    description=(
        "Retrieve analysis results by ID. "
        "Status will be 'processing', 'completed', or 'failed'."
    ),
)
async def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """
    Retrieve analysis results by analysis_id.

    Returns the current status and recommendations if processing is complete.
    Poll this endpoint until status is 'completed' or 'failed'.

    Args:
        analysis_id: UUID returned by POST /api/analyze
        db: Database session (injected)

    Returns:
        AnalyzeResponse — status='processing' if still running,
        'completed' with recommendations if done, 'failed' if errored

    Raises:
        HTTPException: 404 if analysis_id not found
    """
    try:
        query = db.query(Query).filter(Query.analysis_id == analysis_id).first()

        if query is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis {analysis_id} not found",
            )

        # Still processing — return early with no recommendations yet
        if query.status == "processing":
            return AnalyzeResponse(
                analysis_id=query.analysis_id,
                status="processing",
                recommendations=[],
                similar_queries=[],
                created_at=query.created_at,
            )

        # Completed — fetch and return stored recommendations
        optimizations = db.query(Optimization).filter(
            Optimization.query_id == query.id
        ).all()

        recommendations = [
            Recommendation(
                type=opt.recommendation_type,
                description=opt.recommendation_text,
                sql=None,
                predicted_improvement=f"{opt.predicted_improvement_percent}%",
            )
            for opt in optimizations
        ]

        return AnalyzeResponse(
            analysis_id=query.analysis_id,
            status=query.status,
            recommendations=recommendations,
            similar_queries=[],
            created_at=query.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis",
        )
