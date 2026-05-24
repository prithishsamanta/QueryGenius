# Database Standards - PostgreSQL & pgvector

## Core Principles
<principles>
1. **ORM Always**: Use SQLAlchemy, never raw SQL strings
2. **Migrations Matter**: Track all schema changes with Alembic
3. **Type Safety**: Use proper SQLAlchemy types for all columns
4. **Index Strategy**: Index foreign keys and frequently queried columns
5. **Vector Operations**: Use pgvector extension for similarity search
</principles>

## SQLAlchemy Models
<sqlalchemy_models>
```python
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
    query_text = Column(Text, nullable=False, index=True)
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
```
</sqlalchemy_models>

## Database Setup Script
<setup_script>
```python
# scripts/setup_db.py
"""
Setup PostgreSQL database with pgvector extension.

Run this script once to initialize the database schema.
"""
from sqlalchemy import create_engine, text
from src.models.schemas import Base
import os

def setup_database():
    """Initialize database schema and pgvector extension."""
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    engine = create_engine(database_url)
    
    # Create pgvector extension
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            print("- pgvector extension created")
        except Exception as e:
            print(f"- Failed to create pgvector extension: {e}")
            raise
    
    # Create all tables
    try:
        Base.metadata.create_all(engine)
        print("- Database tables created")
    except Exception as e:
        print(f"- Failed to create tables: {e}")
        raise
    
    # Create vector index
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS queries_embedding_idx "
                "ON queries USING ivfflat (embedding vector_cosine_ops) "
                "WITH (lists = 100);"
            ))
            conn.commit()
            print("- Vector similarity index created")
        except Exception as e:
            print(f"- Failed to create vector index: {e}")
            raise
    
    print("\n- Database setup complete!")

if __name__ == "__main__":
    setup_database()
```
</setup_script>

## pgvector Similarity Search
<pgvector_similarity>
```python
# src/services/similarity.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict
import numpy as np

from src.models.schemas import Query

def find_similar_queries(
    db: Session,
    query_embedding: List[float],
    top_k: int = 5,
    similarity_threshold: float = 0.7
) -> List[Dict]:
    """
    Find similar queries using pgvector cosine similarity.
    
    Args:
        db: Database session
        query_embedding: Vector embedding to search for (384-dim)
        top_k: Number of similar queries to return
        similarity_threshold: Minimum similarity score (0.0-1.0)
        
    Returns:
        List of similar queries with metadata
        
    Example:
        >>> embedding = generate_embedding("SELECT * FROM users")
        >>> similar = find_similar_queries(db, embedding, top_k=3)
        >>> similar[0]['similarity_score']
        0.87
    """
    # Convert embedding to string format for SQL
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    # Use pgvector's <-> operator for cosine distance
    # Lower distance = more similar
    # Convert distance to similarity: similarity = 1 - distance
    query = text("""
        SELECT 
            id,
            query_text,
            execution_time_ms,
            1 - (embedding <-> :embedding::vector) AS similarity_score
        FROM queries
        WHERE 1 - (embedding <-> :embedding::vector) >= :threshold
        ORDER BY embedding <-> :embedding::vector
        LIMIT :limit
    """)
    
    result = db.execute(
        query,
        {
            "embedding": embedding_str,
            "threshold": similarity_threshold,
            "limit": top_k
        }
    )
    
    similar_queries = []
    for row in result:
        similar_queries.append({
            "query_id": row.id,
            "query_text": row.query_text,
            "execution_time_ms": row.execution_time_ms,
            "similarity_score": round(float(row.similarity_score), 3)
        })
    
    return similar_queries
```
</pgvector_similarity>

## Vector Embedding Generation
<embedding_generation>
```python
# src/core/embeddings.py
from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

# Global model instance (load once)
_model = None

def get_embedding_model() -> SentenceTransformer:
    """
    Get or initialize the sentence transformer model.
    
    Returns:
        Loaded SentenceTransformer model
    """
    global _model
    if _model is None:
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        print(f"Loading embedding model: {model_name}...")
        _model = SentenceTransformer(model_name)
        print("- Model loaded")
    return _model

def generate_embedding(text: str) -> List[float]:
    """
    Generate 384-dimensional embedding for text.
    
    Args:
        text: Input text (SQL query)
        
    Returns:
        List of 384 float values representing the embedding
        
    Raises:
        ValueError: If text is empty
        
    Example:
        >>> embedding = generate_embedding("SELECT * FROM users WHERE id = 1")
        >>> len(embedding)
        384
        >>> isinstance(embedding[0], float)
        True
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    
    model = get_embedding_model()
    
    # Generate embedding
    embedding = model.encode(text, convert_to_numpy=True)
    
    # Convert to list of floats
    return embedding.tolist()

def validate_embedding_dimension(embedding: List[float], expected_dim: int = 384):
    """
    Validate embedding has correct dimensions.
    
    Args:
        embedding: Vector embedding to validate
        expected_dim: Expected number of dimensions (default 384)
        
    Raises:
        ValueError: If dimensions don't match
    """
    if len(embedding) != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(embedding)}"
        )
```
</embedding_generation>

## Database Session Management
<session_management>
```python
# Best practices for session handling

# GOOD: Using FastAPI dependency injection
from fastapi import Depends
from src.core.database import get_db

@router.get("/queries")
async def get_queries(db: Session = Depends(get_db)):
    queries = db.query(Query).limit(10).all()
    return queries
    # Session automatically closed by get_db()

# GOOD: Manual session with try/finally
def process_query(query_text: str):
    db = SessionLocal()
    try:
        query = Query(query_text=query_text)
        db.add(query)
        db.commit()
        return query.id
    finally:
        db.close()

# BAD: Session never closed
def bad_example():
    db = SessionLocal()
    query = Query(query_text="SELECT * FROM users")
    db.add(query)
    db.commit()
    # Session leak! Never closed.
```
</session_management>

## Query Optimization Guidelines
<query_optimization>
1. **Always eager load relationships if needed**
```python
# GOOD: Eager load to avoid N+1 queries
queries = db.query(Query).options(
    joinedload(Query.optimizations)
).all()

# BAD: Lazy loading causes N+1 queries
queries = db.query(Query).all()
for q in queries:
    print(q.optimizations)  # Each access = 1 query
```

2. **Use indexes on frequently queried columns**
```python
# Foreign keys
query_id = Column(Integer, ForeignKey("queries.id"), index=True)

# Filter columns
recommendation_type = Column(String(50), index=True)

# Text search columns
query_text = Column(Text, index=True)
```

3. **Limit result sets**
```python
# GOOD: Use pagination
queries = db.query(Query).limit(100).offset(0).all()

# BAD: Load entire table
queries = db.query(Query).all()  # Could be millions of rows
```

4. **Use specific columns, not SELECT ***
```python
# GOOD: Select specific columns
results = db.query(Query.id, Query.query_text).all()

# BAD: Load entire objects when only need IDs
results = db.query(Query).all()
ids = [q.id for q in results]
```
</query_optimization>

## pgvector Index Types
<index_types>
pgvector supports two index types:

1. **IVFFlat** (Inverted File with Flat compression)
   - Best for: General purpose, datasets < 1M vectors
   - Trade-off: Faster build, slightly lower recall
   ```sql
   CREATE INDEX ON queries USING ivfflat (embedding vector_cosine_ops)
   WITH (lists = 100);
   ```

2. **HNSW** (Hierarchical Navigable Small World)
   - Best for: High recall requirements, larger datasets
   - Trade-off: Slower build, better search quality
   ```sql
   CREATE INDEX ON queries USING hnsw (embedding vector_cosine_ops)
   WITH (m = 16, ef_construction = 64);
   ```

For QueryGenius MVP: Use IVFFlat with lists=100
</index_types>

## Database Standards Checklist
<checklist>
- All models inherit from Base
- All columns have explicit types
- Primary keys use autoincrement=True
- Foreign keys have ondelete behavior defined
- Foreign keys are indexed
- DateTime columns have default=datetime.utcnow
- Relationships use back_populates
- Vector columns specify dimension: Vector(384)
- pgvector extension created before first query
- Vector indexes use ivfflat or hnsw
- Sessions are always closed (try/finally or Depends)
- No raw SQL strings (use text() or ORM)
</checklist>

## Anti-Patterns to Avoid
<anti_patterns>
- DON'T use raw SQL strings without text()
- DON'T forget to commit() after add() or update()
- DON'T leave database sessions open
- DON'T query entire tables without LIMIT
- DON'T skip indexes on foreign keys
- DON'T store vectors without pgvector extension
- DON'T use different embedding dimensions
- DON'T forget to validate embedding dimensions
- DON'T use lazy loading for relationships in loops
- DON'T mix ORM queries with raw SQL in same session
</anti_patterns>
