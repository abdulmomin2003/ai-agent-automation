"""
FAISS-based vector store with metadata persistence.

Uses FAISS for fast similarity search and a JSON sidecar file
for metadata storage. Supports add, search, delete, and persistence.
"""

import os
import json
import logging
from typing import Optional

import numpy as np
import faiss

from config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """
    FAISS-backed vector store with persistent storage.

    Stores:
    - FAISS index file: fast cosine similarity search
    - Metadata JSON: document texts, metadata, and ID mapping
    """

    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir or settings.VECTOR_STORE_DIR
        os.makedirs(self.persist_dir, exist_ok=True)

        self.index_path = os.path.join(self.persist_dir, "faiss.index")
        self.meta_path = os.path.join(self.persist_dir, "metadata.json")

        self.dimension = settings.EMBEDDING_DIMENSIONS

        # Internal storage
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metadatas: list[dict] = []
        self._index: Optional[faiss.IndexFlatIP] = None  # Inner product (cosine on normalized vectors)

        # Load existing data if available
        self._load()

    def _load(self) -> None:
        """Load persisted index and metadata from disk."""
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self._index = faiss.read_index(self.index_path)
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self._ids = meta.get("ids", [])
                self._texts = meta.get("texts", [])
                self._metadatas = meta.get("metadatas", [])
                logger.info(
                    f"Loaded {len(self._ids)} documents from {self.persist_dir}"
                )
            except Exception as e:
                logger.error(f"Error loading vector store: {e}")
                self._init_empty()
        else:
            self._init_empty()

    def _init_empty(self) -> None:
        """Initialize an empty FAISS index."""
        # Using IndexFlatIP (inner product) — we normalize vectors so IP == cosine similarity
        self._index = faiss.IndexFlatIP(self.dimension)
        self._ids = []
        self._texts = []
        self._metadatas = []

    def _save(self) -> None:
        """Persist the index and metadata to disk."""
        faiss.write_index(self._index, self.index_path)
        meta = {
            "ids": self._ids,
            "texts": self._texts,
            "metadatas": self._metadatas,
        }
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, default=str)
        logger.info(f"Saved {len(self._ids)} documents to {self.persist_dir}")

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        """L2-normalize vectors so inner product == cosine similarity."""
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return vectors / norms

    def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """Add documents with pre-computed embeddings to the store."""
        if not ids:
            return

        vectors = np.array(embeddings, dtype=np.float32)
        vectors = self._normalize(vectors)

        self._index.add(vectors)
        self._ids.extend(ids)
        self._texts.extend(texts)

        if metadatas:
            # Ensure all metadata values are JSON-serializable
            clean = [
                {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                 for k, v in m.items()}
                for m in metadatas
            ]
            self._metadatas.extend(clean)
        else:
            self._metadatas.extend([{} for _ in ids])

        self._save()
        logger.info(f"Added {len(ids)} documents to vector store")

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """
        Search for similar documents by embedding vector.

        Returns list of dicts with keys: id, text, metadata, distance
        """
        if self._index.ntotal == 0:
            return []

        query_vec = np.array([query_embedding], dtype=np.float32)
        query_vec = self._normalize(query_vec)

        # Search more than top_k if we have a filter, since we'll filter after
        search_k = min(top_k * 3 if where else top_k, self._index.ntotal)
        scores, indices = self._index.search(query_vec, search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._ids):
                continue

            meta = self._metadatas[idx] if idx < len(self._metadatas) else {}

            # Apply metadata filter if specified
            if where:
                match = all(
                    meta.get(k) == v for k, v in where.items()
                )
                if not match:
                    continue

            results.append({
                "id": self._ids[idx],
                "text": self._texts[idx],
                "metadata": meta,
                "distance": float(1.0 - score),  # Convert similarity to distance
            })

            if len(results) >= top_k:
                break

        return results

    def get_all_documents(self) -> list[dict]:
        """Retrieve all documents from the store."""
        return [
            {
                "id": self._ids[i],
                "text": self._texts[i],
                "metadata": self._metadatas[i] if i < len(self._metadatas) else {},
            }
            for i in range(len(self._ids))
        ]

    def delete_by_source(self, source: str) -> int:
        """
        Delete all chunks belonging to a specific source document.
        Rebuilds the FAISS index after deletion.
        """
        # Find indices to keep
        keep_indices = []
        delete_count = 0
        for i in range(len(self._ids)):
            meta = self._metadatas[i] if i < len(self._metadatas) else {}
            if meta.get("source") == source:
                delete_count += 1
            else:
                keep_indices.append(i)

        if delete_count == 0:
            return 0

        # Rebuild everything without deleted entries
        if keep_indices:
            # Reconstruct vectors from the old index
            old_vectors = np.array([
                self._index.reconstruct(i) for i in keep_indices
            ], dtype=np.float32)

            new_ids = [self._ids[i] for i in keep_indices]
            new_texts = [self._texts[i] for i in keep_indices]
            new_metas = [self._metadatas[i] for i in keep_indices]

            self._init_empty()
            self._index.add(old_vectors)
            self._ids = new_ids
            self._texts = new_texts
            self._metadatas = new_metas
        else:
            self._init_empty()

        self._save()
        logger.info(f"Deleted {delete_count} chunks from source: {source}")
        return delete_count

    def clear(self) -> None:
        """Delete all documents from the store."""
        self._init_empty()
        self._save()
        logger.info("Vector store cleared")

    def get_stats(self) -> dict:
        """Get store statistics."""
        sources = set()
        for meta in self._metadatas:
            if meta and "source" in meta:
                sources.add(meta["source"])

        return {
            "total_chunks": len(self._ids),
            "unique_documents": len(sources),
            "sources": sorted(sources),
        }
