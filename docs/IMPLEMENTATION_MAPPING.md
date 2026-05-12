# Report-to-Implementation Mapping

This document maps each section from docs/report.tex to the concrete implementation in the codebase. It also points to the exact files that implement each feature.

## 1) System Overview and Architecture

**Report section:** Introduction + Methodology (System Architecture)

**Implementation:**
- FastAPI backend entry point and routes: [backend/main.py](../backend/main.py)
- Multi-tenant orchestration and per-agent pipelines: [backend/agent_manager.py](../backend/agent_manager.py)
- RAG pipeline and agent orchestration: [backend/rag_pipeline.py](../backend/rag_pipeline.py)
- Frontend dashboard and agent UI: [frontend/src/app/page.tsx](../frontend/src/app/page.tsx), [frontend/src/app/agents/[id]/page.tsx](../frontend/src/app/agents/%5Bid%5D/page.tsx)
- Frontend API client wrapper: [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)

**How it maps:**
- The report describes a multi-tenant platform with a FastAPI backend and Next.js frontend. The FastAPI application and all HTTP + WebSocket endpoints are defined in [backend/main.py](../backend/main.py). The UI surfaces for creating agents, viewing their status, and interacting with chat/voice are implemented in the Next.js pages listed above.
- Per-agent isolation is handled by AgentManager: it creates a RAGPipeline per agent, with an isolated vector store directory tied to the agent ID.

## 2) Document Ingestion

**Report section:** Document Ingestion

**Implementation:**
- Multi-format parsing (PDF, DOCX, PPTX, XLSX/CSV, TXT/MD/HTML/JSON): [backend/document_parser.py](../backend/document_parser.py)
- Token-aware recursive chunking: [backend/chunker.py](../backend/chunker.py)
- Embeddings generation: [backend/embeddings.py](../backend/embeddings.py)
- Vector persistence in FAISS + JSON metadata: [backend/vector_store.py](../backend/vector_store.py)
- Upload endpoint and ingestion trigger: [backend/main.py](../backend/main.py)
- Per-agent ingestion entrypoint: [backend/agent_manager.py](../backend/agent_manager.py)

**How it maps:**
- Upload hits /agents/{agent_id}/upload in [backend/main.py](../backend/main.py), which calls AgentManager.upload_document in [backend/agent_manager.py](../backend/agent_manager.py).
- AgentManager delegates to RAGPipeline.ingest_document in [backend/rag_pipeline.py](../backend/rag_pipeline.py): parse -> chunk -> embed -> store.
- DocumentParser extracts clean text and metadata; TextChunker does recursive splitting with overlap; EmbeddingService produces vector embeddings; VectorStore persists them in a FAISS index + JSON metadata sidecar.

## 3) Embedding and Vector Store

**Report section:** Embedding and Vector Store

**Implementation:**
- Embedding model and batch encoding: [backend/embeddings.py](../backend/embeddings.py)
- FAISS index + metadata JSON store: [backend/vector_store.py](../backend/vector_store.py)
- Config defaults for embedding model and dimensions: [backend/config.py](../backend/config.py)

**How it maps:**
- EmbeddingService uses a sentence-transformers model (default all-MiniLM-L6-v2) configured in [backend/config.py](../backend/config.py).
- VectorStore stores normalized vectors in FAISS for cosine similarity (inner-product on normalized vectors) and keeps a metadata.json file alongside the index.

## 4) Hybrid Retrieval

**Report section:** Hybrid Retrieval

**Implementation:**
- Dense + BM25 + RRF + optional reranking: [backend/retriever.py](../backend/retriever.py)
- Retrieval configuration (weights, top-k): [backend/config.py](../backend/config.py)

**How it maps:**
- HybridRetriever runs semantic retrieval via embeddings + vector search, BM25 sparse retrieval, merges via RRF, and optionally reranks with a cross-encoder.
- RRF weights are exposed in config (BM25_WEIGHT, SEMANTIC_WEIGHT).
- The reranker uses cross-encoder/ms-marco-MiniLM-L-6-v2 by default.

## 5) Generation and Agentic Tool Use

**Report section:** Generation and Agentic Tool Use + LangGraph Workflow

**Implementation:**
- LangGraph tool loop and built-in tools: [backend/agentic_workflow.py](../backend/agentic_workflow.py)
- RAG pipeline query and tool-callback wiring: [backend/rag_pipeline.py](../backend/rag_pipeline.py)

**How it maps:**
- create_agentic_workflow defines the agent state machine and the tools: search_knowledge_base, send_email, check_available_slots, book_appointment, cancel_appointment, plus custom tools from the DB.
- RAGPipeline.query converts conversation history to LangChain messages and invokes the LangGraph workflow. Tool output is captured and used to infer sources.

## 6) Multi-Tenant Agent Management

**Report section:** Contributions (multi-tenant manager and isolated KBs)

**Implementation:**
- Agent CRUD and pipeline caching: [backend/agent_manager.py](../backend/agent_manager.py)
- Agent DB schema and CRUD: [backend/db/database.py](../backend/db/database.py)
- Request/response models: [backend/db/models.py](../backend/db/models.py)

**How it maps:**
- Each agent is stored in the database and has its own vector store directory. AgentManager caches a RAGPipeline per agent and invalidates it on configuration changes.

## 7) Chat, Voice, and WhatsApp Channels

**Report section:** System Architecture + Voice / Automation references

**Implementation:**
- Web chat endpoint: [backend/main.py](../backend/main.py)
- Web UI chat and voice capture: [frontend/src/app/agents/[id]/page.tsx](../frontend/src/app/agents/%5Bid%5D/page.tsx)
- Voice query endpoint (upload audio -> STT -> RAG -> TTS): [backend/main.py](../backend/main.py)
- Twilio Media Streams (real-time voice): [backend/voice_stream.py](../backend/voice_stream.py)
- Web browser realtime voice (WebSocket PCM): [backend/web_voice_stream.py](../backend/web_voice_stream.py)
- STT via Groq Whisper + TTS generation: [backend/audio_service.py](../backend/audio_service.py), [backend/tts_service.py](../backend/tts_service.py)
- Twilio voice webhooks and intents: [backend/twilio_service.py](../backend/twilio_service.py)
- WhatsApp webhook handling: [backend/main.py](../backend/main.py), [backend/whatsapp_service.py](../backend/whatsapp_service.py)

**How it maps:**
- Web chat uses /agents/{id}/chat and the frontend API client.
- Voice uploads (audio/webm) are transcribed and answered via the RAG pipeline, then TTS audio is generated and returned.
- Twilio voice uses Media Streams over WebSocket for near real-time bi-directional audio.
- Web browser voice uses a WebSocket streaming path with VAD and partial transcription updates.
- WhatsApp inbound messages are processed through the same agent chat pipeline and returned as TwiML responses.

## 8) Email and Scheduling Tools

**Report section:** Agentic Tool Use (scheduling and follow-up)

**Implementation:**
- Email service and HTML templates: [backend/email_service.py](../backend/email_service.py)
- Booking and availability tools: [backend/agentic_workflow.py](../backend/agentic_workflow.py)
- Booking data storage: [backend/db/database.py](../backend/db/database.py)

**How it maps:**
- The send_email tool uses SendGrid and can be triggered by LangGraph.
- Availability, booking, and cancellation use DB helpers for scheduling and update confirmation emails.

## 9) Evaluation and SciFact Metrics

**Report section:** Experimental Results

**Implementation:**
- SciFact evaluation script: [backend/scripts/eval_scifact.py](../backend/scripts/eval_scifact.py)
- Result output location: data/beir/scifact_eval_metrics.json

**How it maps:**
- The script evaluates dense-only, BM25-only, hybrid (no rerank), and hybrid + rerank, which matches the methods in the report.
- Note: the script currently sets MAX_QUERIES = 10 and MAX_DOCS = 200 for speed. If you want the report-scale numbers (first 100 queries), update MAX_QUERIES to 100 and adjust MAX_DOCS as needed.

## 10) Configuration Defaults

**Report section:** Methods and Implementation Defaults

**Implementation:**
- All defaults for chunking, retrieval weights, and model choices: [backend/config.py](../backend/config.py)

**How it maps:**
- Chunk size and overlap match the report description (token-aware splitting with overlap).
- Reranker, embedding model, and retrieval weights are set in one place and used throughout the pipeline.

---

If you want, I can also add a small table that cross-references each report subsection to specific functions and classes (per-file and per-function mapping).
