# src/services/analyzer.py
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.schemas import Query
from src.tasks.analysis_task import run_analysis


class AnalyzerService:
    """Service for query analysis operations."""

    def __init__(self, db: Session):
        self.db = db

    def submit(
        self,
        query_text: str,
        execution_time_ms: float,
        execution_plan: Optional[Dict] = None,
        schema_context: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Create a query record and enqueue it for async analysis.

        Stores the query immediately with status='processing' and a
        placeholder embedding, then hands off the heavy work (embedding
        generation, similarity search, LLM call) to a Celery worker.
        Returns instantly so the HTTP connection is not held open.

        Args:
            query_text: SQL query to analyze
            execution_time_ms: Execution time in milliseconds
            execution_plan: Optional EXPLAIN ANALYZE output
            schema_context: Optional table schema dicts for precise recommendations

        Returns:
            Dict with analysis_id, status, and created_at
        """
        analysis_id = str(uuid.uuid4())

        # Insert the row immediately with status=processing
        # embedding is null until the Celery task fills it in
        query = Query(
            analysis_id=analysis_id,
            status="processing",
            query_text=query_text,
            execution_time_ms=execution_time_ms,
            execution_plan=execution_plan,
            created_at=datetime.utcnow(),
            embedding=None,
        )
        self.db.add(query)
        self.db.commit()
        self.db.refresh(query)

        # Enqueue the analysis task — worker picks it up independently
        run_analysis.delay(
            analysis_id=analysis_id,
            query_text=query_text,
            execution_time_ms=execution_time_ms,
            execution_plan=execution_plan,
            schema_context=schema_context,
        )

        return {
            "analysis_id": analysis_id,
            "status": "processing",
            "created_at": query.created_at,
        }
