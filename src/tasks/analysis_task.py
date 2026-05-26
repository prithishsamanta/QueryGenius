# src/tasks/analysis_task.py
import logging
from typing import Dict, List, Optional

from src.core.celery_app import celery_app
from src.core.database import SessionLocal
from src.core.embeddings import generate_embedding
from src.models.schemas import Query, Optimization
from src.services.similarity import find_similar_queries
from src.services.llm import mock_analyze_with_claude

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="src.tasks.analysis_task.run_analysis",
    max_retries=3,
    default_retry_delay=2,
)
def run_analysis(
    self,
    analysis_id: str,
    query_text: str,
    execution_time_ms: float,
    execution_plan: Optional[Dict],
    schema_context: Optional[List[Dict]],
) -> Dict:
    """
    Celery task that runs the full query analysis pipeline asynchronously.

    Picks up the pre-created Query row (status=processing), generates the
    embedding, runs pgvector similarity search, calls the LLM, stores
    recommendations, and marks the row as completed or failed.

    Args:
        analysis_id: UUID of the pre-created Query row
        query_text: SQL query to analyze
        execution_time_ms: Execution time in milliseconds
        execution_plan: Optional EXPLAIN ANALYZE output
        schema_context: Optional table schema dicts for precise recommendations

    Returns:
        Dict with analysis_id and status

    Raises:
        Retries up to 3 times on failure with 2s base delay
    """
    db = SessionLocal()
    try:
        # Fetch the pre-created row
        query = db.query(Query).filter(Query.analysis_id == analysis_id).first()
        if query is None:
            logger.error(f"Query row not found for analysis_id={analysis_id}")
            return {"analysis_id": analysis_id, "status": "failed"}

        # 1. Generate embedding and store it
        embedding = generate_embedding(query_text)
        query.embedding = embedding
        db.commit()

        # 2. Find similar historical queries
        similar = find_similar_queries(db, embedding, top_k=3)

        # 3. Get recommendations from LLM
        # mock_analyze_with_claude is async — run it in a fresh event loop
        # since Celery workers run synchronously
        import asyncio
        recommendations = asyncio.run(
            mock_analyze_with_claude(
                query_text=query_text,
                execution_plan=execution_plan,
                similar_queries=similar,
                schema_context=schema_context,
            )
        )

        # 4. Store recommendations
        for rec in recommendations:
            opt = Optimization(
                query_id=query.id,
                recommendation_type=rec["type"],
                recommendation_text=rec["description"],
                predicted_improvement_percent=float(
                    rec["predicted_improvement"].rstrip("%")
                ),
            )
            db.add(opt)

        # 5. Mark as completed
        query.status = "completed"
        db.commit()

        logger.info(f"Analysis completed for analysis_id={analysis_id}")
        return {"analysis_id": analysis_id, "status": "completed"}

    except Exception as exc:
        db.rollback()
        logger.error(f"Analysis failed for analysis_id={analysis_id}: {exc}")

        # Mark the row as failed before retrying
        try:
            query = db.query(Query).filter(Query.analysis_id == analysis_id).first()
            if query:
                query.status = "failed"
                db.commit()
        except Exception:
            pass

        # Retry with exponential backoff: 2s, 4s, 8s
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    finally:
        db.close()
