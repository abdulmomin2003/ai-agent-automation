"""
Embedding generation using OpenAI API.

Handles batching, rate limiting, and caching for efficient embedding creation.
"""

import logging
from typing import Optional

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generate embeddings using OpenAI's embedding models.
    Supports batching for efficient processing of large document sets.
    """

    MAX_BATCH_SIZE = 100  # OpenAI batch limit

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text string."""
        response = self.client.embeddings.create(
            input=text,
            model=self.model,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.
        Automatically handles splitting into sub-batches if needed.
        """
        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            logger.info(
                f"Embedding batch {i // self.MAX_BATCH_SIZE + 1} "
                f"({len(batch)} texts)"
            )

            response = self.client.embeddings.create(
                input=batch,
                model=self.model,
            )

            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [d.embedding for d in sorted_data]
            all_embeddings.extend(batch_embeddings)

        logger.info(f"Generated {len(all_embeddings)} embeddings total")
        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a search query."""
        return self.embed_text(query)
