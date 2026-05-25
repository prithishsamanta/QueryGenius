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
        execution_plan: Dict = None,
        schema_context: List[Dict] = None,
    ) -> Dict:
        """
        Analyze a query and return recommendations.

        Args:
            query_text: SQL query to analyze
            execution_time_ms: Execution time in milliseconds
            execution_plan: Optional EXPLAIN output
            schema_context: Optional table schema dicts for precise recommendations

        Returns:
            Analysis result with recommendations
        """
        # Generate UUID first so it can be stored and returned consistently
        analysis_id = str(uuid.uuid4())

        # 1. Generate embedding
        embedding = generate_embedding(query_text)

        # 2. Store query in database with the analysis_id
        query = Query(
            analysis_id=analysis_id,
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
            similar_queries=similar,
            schema_context=schema_context,
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
            "analysis_id": analysis_id,
            "status": "completed",
            "recommendations": recommendations,
            "similar_queries": similar,
            "created_at": query.created_at
        }