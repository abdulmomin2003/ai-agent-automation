"""
Hybrid retriever with BM25 + Semantic search + Cross-encoder reranking.

This is the core accuracy module. It combines:
1. Dense retrieval (embeddings / cosine similarity)
2. Sparse retrieval (BM25 keyword matching)
3. Reciprocal Rank Fusion (RRF) to merge results
4. Cross-encoder reranking for final precision
"""

import re
import logging
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from config import settings
from embeddings import EmbeddingService
from vector_store import VectorStore

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    High-accuracy retriever combining multiple strategies:

    1. Semantic Search: Embed query → cosine similarity against ChromaDB
    2. BM25 Keyword Search: Token-level matching for exact terms
    3. Reciprocal Rank Fusion: Merge rankings from both methods
    4. Cross-Encoder Reranking: Score (query, passage) pairs for precision

    This approach significantly outperforms single-strategy retrieval.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        reranker_model: Optional[str] = None,
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service

        # Initialize cross-encoder reranker
        model_name = reranker_model or settings.RERANKER_MODEL
        logger.info(f"Loading reranker model: {model_name}")
        self.reranker = CrossEncoder(model_name)
        logger.info("Reranker loaded successfully")

        # BM25 index (rebuilt when documents change)
        self._bm25_index: Optional[BM25Okapi] = None
        self._bm25_docs: list[dict] = []

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer for BM25."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        tokens = text.split()
        # Remove very short tokens
        return [t for t in tokens if len(t) > 1]

    def _build_bm25_index(self) -> None:
        """Build BM25 index from all documents in the vector store."""
        self._bm25_docs = self.vector_store.get_all_documents()
        if not self._bm25_docs:
            self._bm25_index = None
            return

        tokenized_corpus = [
            self._tokenize(doc["text"]) for doc in self._bm25_docs
        ]
        self._bm25_index = BM25Okapi(tokenized_corpus)
        logger.info(f"BM25 index built with {len(self._bm25_docs)} documents")

    def refresh_index(self) -> None:
        """Manually refresh the BM25 index after document changes."""
        self._build_bm25_index()

    def _semantic_search(
        self, query: str, top_k: int
    ) -> list[dict]:
        """Dense retrieval using embeddings."""
        query_embedding = self.embedding_service.embed_query(query)
        results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
        )
        # Convert distance to score (lower distance = higher score)
        for r in results:
            r["score"] = 1.0 - r.get("distance", 0)
        return results

    def _bm25_search(
        self, query: str, top_k: int
    ) -> list[dict]:
        """Sparse retrieval using BM25."""
        if self._bm25_index is None:
            self._build_bm25_index()

        if not self._bm25_index or not self._bm25_docs:
            return []

        query_tokens = self._tokenize(query)
        scores = self._bm25_index.get_scores(query_tokens)

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                doc = self._bm25_docs[idx].copy()
                doc["score"] = float(scores[idx])
                results.append(doc)

        return results

    def _reciprocal_rank_fusion(
        self,
        semantic_results: list[dict],
        bm25_results: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """
        Merge results from semantic and BM25 using Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank_i)) across all rankings.
        This is more robust than simple score averaging since the score
        scales of semantic and BM25 are very different.
        """
        doc_scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}

        # Score from semantic results
        for rank, doc in enumerate(semantic_results):
            doc_id = doc["id"]
            rrf_score = settings.SEMANTIC_WEIGHT / (k + rank + 1)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + rrf_score
            doc_map[doc_id] = doc

        # Score from BM25 results
        for rank, doc in enumerate(bm25_results):
            doc_id = doc["id"]
            rrf_score = settings.BM25_WEIGHT / (k + rank + 1)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + rrf_score
            if doc_id not in doc_map:
                doc_map[doc_id] = doc

        # Sort by fused score
        sorted_ids = sorted(
            doc_scores.keys(),
            key=lambda x: doc_scores[x],
            reverse=True,
        )

        results = []
        for doc_id in sorted_ids:
            doc = doc_map[doc_id].copy()
            doc["rrf_score"] = doc_scores[doc_id]
            results.append(doc)

        return results

    def _rerank(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        """
        Rerank documents using a cross-encoder model.

        Cross-encoders score (query, passage) pairs jointly, providing
        much higher accuracy than bi-encoder similarity alone.
        """
        if not documents:
            return []

        # Prepare pairs for the cross-encoder
        pairs = [(query, doc["text"]) for doc in documents]
        scores = self.reranker.predict(pairs)

        # Attach scores and sort
        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        reranked = sorted(
            documents,
            key=lambda x: x["rerank_score"],
            reverse=True,
        )

        return reranked[:top_k]

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        use_reranking: bool = True,
    ) -> list[dict]:
        """
        Full hybrid retrieval pipeline:
        1. Semantic search → top candidates
        2. BM25 keyword search → top candidates
        3. Reciprocal Rank Fusion → merged ranking
        4. Cross-encoder reranking → final top-k

        Args:
            query: The search query.
            top_k: Number of final results (default from settings).
            use_reranking: Whether to apply cross-encoder reranking.

        Returns:
            List of dicts with keys: id, text, metadata, rerank_score
        """
        final_k = top_k or settings.TOP_K_RERANK
        retrieval_k = settings.TOP_K_RETRIEVAL

        logger.info(f"Retrieving for query: '{query[:80]}...'")

        # Step 1 & 2: Dual retrieval
        semantic_results = self._semantic_search(query, retrieval_k)
        bm25_results = self._bm25_search(query, retrieval_k)

        logger.info(
            f"Semantic: {len(semantic_results)} results, "
            f"BM25: {len(bm25_results)} results"
        )

        # Step 3: Fuse results
        fused = self._reciprocal_rank_fusion(
            semantic_results, bm25_results
        )

        if not fused:
            return []

        # Step 4: Rerank top candidates
        if use_reranking and len(fused) > 0:
            # Rerank the top candidates (more than final_k for better selection)
            candidates = fused[: max(retrieval_k, final_k * 2)]
            results = self._rerank(query, candidates, final_k)
            logger.info(
                f"Reranked to {len(results)} results "
                f"(top score: {results[0]['rerank_score']:.4f})"
            )
        else:
            results = fused[:final_k]

        return results
