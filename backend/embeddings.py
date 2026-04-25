"""
Embedding generation using HuggingFace Sentence Transformers.

Handles local embedding generation using lightweight models.
"""

import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generate embeddings using local sentence-transformers models.
    """

    def __init__(self, api_key: Optional[str] = None):
        # API key is ignored for local embeddings, kept for API compatibility
        self.model_name = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        logger.info(f"Loading embedding model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        logger.info("Embedding model loaded successfully")

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text string."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.
        """
        if not texts:
            return []

        logger.info(f"Embedding batch of {len(texts)} texts")
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a search query."""
        return self.embed_text(query)
