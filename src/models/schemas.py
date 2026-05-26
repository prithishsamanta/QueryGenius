# src/models/schemas.py
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class Query(Base):
    """
    Stores analyzed PostgreSQL queries with vector embeddings.

    Attributes:
        id: Primary key
        query_text: The SQL query text
        execution_time_ms: Query execution time in milliseconds
        execution_plan: EXPLAIN ANALYZE output as JSON
        database_name: Source database name
        created_at: Timestamp of analysis
        embedding: Vector embedding (384 dimensions) for similarity search
    """
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(36), nullable=False, unique=True, index=True)
    query_text = Column(Text, nullable=False)
    execution_time_ms = Column(Float, nullable=True)
    execution_plan = Column(JSON, nullable=True)
    database_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    embedding = Column(Vector(384), nullable=False)

    # Relationships
    optimizations = relationship("Optimization", back_populates="query", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Query(id={self.id}, query_text={self.query_text[:50]}...)>"

class Optimization(Base):
    """
    Stores optimization recommendations for queries.

    Attributes:
        id: Primary key
        query_id: Foreign key to queries table
        recommendation_type: Type of optimization (index, rewrite, schema)
        recommendation_text: Human-readable recommendation
        predicted_improvement_percent: Expected performance gain
        created_at: Timestamp of recommendation
    """
    __tablename__ = "optimizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("queries.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_type = Column(String(50), nullable=False, index=True)
    recommendation_text = Column(Text, nullable=False)
    predicted_improvement_percent = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    query = relationship("Query", back_populates="optimizations")

    def __repr__(self):
        return f"<Optimization(id={self.id}, type={self.recommendation_type})>"