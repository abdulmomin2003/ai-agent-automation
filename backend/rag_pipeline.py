"""
RAG pipeline — ties together document processing, retrieval, and generation.

This is the main orchestrator that:
1. Ingests documents (parse → chunk → embed → store)
2. Handles queries (retrieve → format context → generate response)
"""

import os
import uuid
import logging
from typing import Optional

from groq import Groq

from config import settings
from document_parser import DocumentParser, ParsedDocument
from chunker import TextChunker, Chunk
from embeddings import EmbeddingService
from vector_store import VectorStore
from retriever import HybridRetriever

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a helpful, accurate assistant that answers questions based on the provided context documents.

IMPORTANT RULES:
1. Answer ONLY based on the provided context. Do not make up information.
2. If the context does not contain enough information to answer the question, say:
   "I don't have enough information in the uploaded documents to answer this question."
3. When referencing information, mention the source document when available.
4. Be concise but thorough. Provide complete answers.
5. If the context contains tables or structured data, present them clearly.
6. If multiple documents contain relevant information, synthesize them into a coherent answer.
"""


class RAGPipeline:
    """
    Complete RAG (Retrieval-Augmented Generation) pipeline.

    Handles the full lifecycle:
    - Document ingestion: parse → chunk → embed → store
    - Query answering: retrieve → context assembly → LLM generation
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        if not self.api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY in .env"
            )

        # Initialize components
        self.parser = DocumentParser()
        self.chunker = TextChunker()
        self.embedding_service = EmbeddingService(api_key=self.api_key)
        self.vector_store = VectorStore()
        self.retriever = HybridRetriever(
            vector_store=self.vector_store,
            embedding_service=self.embedding_service,
        )
        self.llm_client = Groq(api_key=self.api_key)

        # Ensure upload directory exists
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

        logger.info("RAG Pipeline initialized")

    # ── Document Ingestion ─────────────────────────────────────────

    def ingest_document(self, file_path: str) -> dict:
        """
        Full document ingestion pipeline:
        1. Parse the document (any supported format)
        2. Split into semantic chunks
        3. Generate embeddings
        4. Store in vector database

        Returns summary of the ingestion.
        """
        logger.info(f"Ingesting document: {file_path}")

        # Step 1: Parse
        parsed_doc = self.parser.parse(file_path)
        if not parsed_doc.content.strip():
            raise ValueError(f"No text content extracted from {file_path}")

        # Step 2: Chunk
        chunks = self.chunker.chunk_text(
            text=parsed_doc.content,
            metadata=parsed_doc.metadata,
        )

        if not chunks:
            raise ValueError(f"No chunks created from {file_path}")

        # Step 3: Embed
        chunk_texts = [c.text for c in chunks]
        embeddings = self.embedding_service.embed_batch(chunk_texts)

        # Step 4: Store
        chunk_ids = [
            f"{parsed_doc.filename}_{c.chunk_index}_{uuid.uuid4().hex[:8]}"
            for c in chunks
        ]
        metadatas = [c.metadata for c in chunks]

        self.vector_store.add_documents(
            ids=chunk_ids,
            texts=chunk_texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Refresh BM25 index
        self.retriever.refresh_index()

        summary = {
            "filename": parsed_doc.filename,
            "file_type": parsed_doc.file_type,
            "total_chars": len(parsed_doc.content),
            "total_chunks": len(chunks),
            "avg_chunk_tokens": sum(c.token_count for c in chunks) // max(len(chunks), 1),
        }

        logger.info(f"Ingestion complete: {summary}")
        return summary

    def ingest_text(self, text: str, source_name: str = "direct_input") -> dict:
        """Ingest raw text directly (for pasting text or API input)."""
        if not text.strip():
            raise ValueError("Empty text provided")

        metadata = {"source": source_name, "file_type": "text"}
        chunks = self.chunker.chunk_text(text=text, metadata=metadata)

        if not chunks:
            raise ValueError("No chunks created from text")

        chunk_texts = [c.text for c in chunks]
        embeddings = self.embedding_service.embed_batch(chunk_texts)

        chunk_ids = [
            f"{source_name}_{c.chunk_index}_{uuid.uuid4().hex[:8]}"
            for c in chunks
        ]
        metadatas = [c.metadata for c in chunks]

        self.vector_store.add_documents(
            ids=chunk_ids,
            texts=chunk_texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        self.retriever.refresh_index()

        return {
            "source": source_name,
            "total_chars": len(text),
            "total_chunks": len(chunks),
        }

    # ── Query & Generation ─────────────────────────────────────────

    def query(
        self,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        top_k: int = 5,
        use_reranking: bool = True,
    ) -> dict:
        """
        Answer a question using the RAG pipeline:
        1. Retrieve relevant chunks (hybrid + rerank)
        2. Assemble context with source attribution
        3. Generate answer via LLM

        Args:
            question: The user's question.
            conversation_history: List of prior messages [{role, content}].
            top_k: Number of context chunks to use.
            use_reranking: Whether to apply cross-encoder reranking.

        Returns:
            Dict with 'answer', 'sources', and 'context_chunks'.
        """
        logger.info(f"Query: '{question[:100]}'")

        # Step 1: Retrieve
        retrieved = self.retriever.retrieve(
            query=question,
            top_k=top_k,
            use_reranking=use_reranking,
        )

        if not retrieved:
            return {
                "answer": "I don't have any documents in my knowledge base yet. "
                          "Please upload some documents first.",
                "sources": [],
                "context_chunks": [],
            }

        # Step 2: Format context
        context = self._format_context(retrieved)
        sources = self._extract_sources(retrieved)

        # Step 3: Generate answer
        answer = self._generate_answer(
            question=question,
            context=context,
            conversation_history=conversation_history,
        )

        return {
            "answer": answer,
            "sources": sources,
            "context_chunks": [
                {
                    "text": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"],
                    "source": r.get("metadata", {}).get("source", "unknown"),
                    "score": round(r.get("rerank_score", r.get("rrf_score", 0)), 4),
                }
                for r in retrieved
            ],
        }

    def _format_context(self, retrieved: list[dict]) -> str:
        """Format retrieved chunks into a context string for the LLM."""
        context_parts = []
        for i, doc in enumerate(retrieved):
            source = doc.get("metadata", {}).get("source", "unknown")
            chunk_idx = doc.get("metadata", {}).get("chunk_index", "?")
            text = doc["text"]
            context_parts.append(
                f"[Source: {source} | Chunk {chunk_idx}]\n{text}"
            )

        return "\n\n---\n\n".join(context_parts)

    def _extract_sources(self, retrieved: list[dict]) -> list[str]:
        """Extract unique source document names from retrieved chunks."""
        sources = set()
        for doc in retrieved:
            source = doc.get("metadata", {}).get("source", "")
            if source:
                sources.add(source)
        return sorted(sources)

    def _generate_answer(
        self,
        question: str,
        context: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> str:
        """Generate an answer using the LLM with retrieved context."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # Add conversation history if available
        if conversation_history:
            # Keep last 6 messages for context window management
            for msg in conversation_history[-6:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        # Add context and question
        user_message = (
            f"Context from uploaded documents:\n\n{context}\n\n"
            f"---\n\n"
            f"Question: {question}"
        )
        messages.append({"role": "user", "content": user_message})

        response = self.llm_client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.1,  # Low temperature for factual accuracy
            max_tokens=1024,
        )

        return response.choices[0].message.content

    # ── Management ─────────────────────────────────────────────────

    def delete_document(self, source_name: str) -> int:
        """Delete a document and all its chunks from the store."""
        count = self.vector_store.delete_by_source(source_name)
        self.retriever.refresh_index()
        return count

    def clear_all(self) -> None:
        """Clear all documents from the knowledge base."""
        self.vector_store.clear()
        self.retriever.refresh_index()

    def get_stats(self) -> dict:
        """Get knowledge base statistics."""
        return self.vector_store.get_stats()
