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