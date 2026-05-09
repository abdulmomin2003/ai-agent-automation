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
from agentic_workflow import create_agentic_workflow
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a helpful, accurate assistant that answers questions based on the provided context documents.

IMPORTANT RULES:
1. You MUST use the `search_knowledge_base` tool to retrieve relevant context BEFORE answering any factual questions about the business, clinic, or policies.
2. Answer ONLY based on the retrieved context. Do not make up information.
3. If the retrieved context does not contain enough information to answer the question, say:
   "I don't have enough information in the uploaded documents to answer this question."
4. When referencing information, mention the source document when available.
5. Be concise but thorough. Provide complete answers.
"""


class ToolCallbackHandler(BaseCallbackHandler):
    """Callback handler to intercept tool executions."""
    def __init__(self, on_tool_call):
        self.on_tool_call = on_tool_call

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        tool_name = serialized.get("name", "")
        if self.on_tool_call and tool_name:
            self.on_tool_call(tool_name)

class RAGPipeline:
    """
    Complete RAG (Retrieval-Augmented Generation) pipeline.

    Handles the full lifecycle:
    - Document ingestion: parse → chunk → embed → store
    - Query answering: retrieve → context assembly → LLM generation
    """

    def __init__(self, api_key: Optional[str] = None,
                 vector_store_dir: Optional[str] = None,
                 system_prompt: Optional[str] = None,
                 custom_tools: Optional[list[dict]] = None,
                 agent_id: Optional[str] = None,
                 agent_name: str = "AI Agent"):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.agent_id = agent_id
        self.agent_name = agent_name
        if not self.api_key:
            logger.warning(
                "Groq API key not provided; running in local fallback mode (no remote LLM)."
            )

        # Custom system prompt (per-agent) or default
        self.system_prompt = system_prompt or SYSTEM_PROMPT

        # Initialize components
        self.parser = DocumentParser()
        self.chunker = TextChunker()
        self.embedding_service = EmbeddingService(api_key=self.api_key)
        self.vector_store = VectorStore(persist_dir=vector_store_dir)
        self.retriever = HybridRetriever(
            vector_store=self.vector_store,
            embedding_service=self.embedding_service,
        )
        try:
            # Initialize LangGraph workflow with agent context
            self.agent_workflow = create_agentic_workflow(
                retriever=self.retriever,
                api_key=self.api_key,
                custom_tools=custom_tools,
                agent_id=agent_id,
                agent_name=agent_name,
            ) if self.api_key else None
        except Exception as e:
            logger.warning("Failed to initialize LangGraph workflow; LLM disabled: %s", e)
            self.agent_workflow = None

        # Ensure upload directory exists
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

        logger.info("RAG Pipeline initialized (vector_dir=%s, agent_id=%s)", vector_store_dir or 'default', agent_id)

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
        on_tool_call: Optional[callable] = None,
    ) -> dict:
        """
        Answer a question using the LangGraph agentic workflow:
        1. Formulate state with history and question
        2. Agent decides to use tools (like retrieval) or answer directly
        3. Returns the final answer
        """
        logger.info(f"Query (LangGraph): '{question[:100]}'")

        if not self.agent_workflow:
            return {
                "answer": "(LLM disabled) No LLM available to generate an answer.",
                "sources": [],
                "context_chunks": [],
            }

        # Convert conversation history to LangChain messages
        messages = []
        if conversation_history:
            for msg in conversation_history[-6:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Add the current question
        messages.append(HumanMessage(content=question))

        state = {
            "messages": messages,
            "system_prompt": self.system_prompt,
            "context_chunks": [],
            "agent_id": self.agent_id or "",
        }

        # Configure callbacks
        config = {}
        if on_tool_call:
            config["callbacks"] = [ToolCallbackHandler(on_tool_call)]

        # Invoke the LangGraph workflow
        result = self.agent_workflow.invoke(state, config=config)
        
        final_messages = result.get("messages", [])
        if not final_messages:
            return {
                "answer": "Failed to generate an answer.",
                "sources": [],
                "context_chunks": [],
            }

        final_answer = final_messages[-1].content

        # Since the retriever is now a tool, tracking exact sources used is slightly different.
        # We can look for ToolMessages in the result to see what was retrieved.
        sources = set()
        for msg in final_messages:
            if getattr(msg, "type", "") == "tool" and msg.name == "search_knowledge_base":
                # Very basic source extraction from tool output string
                lines = str(msg.content).split("\\n")
                for line in lines:
                    if line.startswith("Source:"):
                        sources.add(line.replace("Source:", "").strip())
                        
        return {
            "answer": final_answer,
            "sources": sorted(list(sources)),
            "context_chunks": [], # Currently handled by tool internally
        }

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
