"""
FastAPI application — REST API for the RAG pipeline.

Endpoints:
- POST /upload        — Upload and ingest a document
- POST /query         — Ask a question against the knowledge base
- POST /ingest-text   — Ingest raw text directly
- GET  /documents     — List ingested documents
- DELETE /documents   — Delete a specific document or clear all
- GET  /health        — Health check
"""

import os
import shutil
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from rag_pipeline import RAGPipeline
from audio_service import AudioService
from supabase_health import check_postgres, check_supabase_http

# ── Logging Setup ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global Services ───────────────────────────────────────────────

rag: Optional[RAGPipeline] = None
audio_svc: Optional[AudioService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize pipelines on startup."""
    global rag, audio_svc
    try:
        rag = RAGPipeline()
        audio_svc = AudioService()
        logger.info("Services ready")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
    yield
    logger.info("Shutting down")


# ── FastAPI App ────────────────────────────────────────────────────

app = FastAPI(
    title="AI Sales Agent — RAG API",
    description="Multi-format document ingestion and high-accuracy RAG query API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ──────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    conversation_history: Optional[list[dict]] = None
    top_k: int = 5
    use_reranking: bool = True


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    context_chunks: list[dict]


class IngestTextRequest(BaseModel):
    text: str
    source_name: str = "direct_input"


class DeleteRequest(BaseModel):
    source_name: Optional[str] = None
    clear_all: bool = False


# ── Endpoints ──────────────────────────────────────────────────────

@app.get("/health")
async def health_check(detail: bool = False):
    """Health check endpoint."""
    supabase_http = check_supabase_http()
    postgres = check_postgres()
    payload = {
        "status": "ok",
        "rag_initialized": rag is not None,
        "supabase_connected": supabase_http.ok and postgres.ok,
        "supabase": {
            "url": settings.supabase_url,
            "project_ref": settings.supabase_project_ref,
            "http_ok": supabase_http.ok,
            "postgres_ok": postgres.ok,
        },
        "stats": rag.get_stats() if rag else None,
    }

    if detail:
        payload["supabase"]["http"] = {
            "ok": supabase_http.ok,
            "detail": supabase_http.detail,
            "data": supabase_http.data,
        }
        payload["supabase"]["postgres"] = {
            "ok": postgres.ok,
            "detail": postgres.detail,
            "data": postgres.data,
        }

    return payload


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and ingest a document into the knowledge base.

    Supports: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, HTML, JSON
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline not initialized. Check your Groq API key.",
        )

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {
        ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls",
        ".csv", ".txt", ".md", ".html", ".htm", ".json",
        ".rtf", ".log", ".xml",
    }:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}",
        )

    # Save uploaded file
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, file.filename)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Ingest the document
        result = rag.ingest_document(file_path)

        return {
            "status": "success",
            "message": f"Document '{file.filename}' ingested successfully",
            **result,
        }

    except Exception as e:
        logger.error(f"Error ingesting {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
async def query_knowledge_base(request: QueryRequest):
    """
    Ask a question against the ingested knowledge base.

    Uses hybrid retrieval (semantic + BM25) with cross-encoder reranking
    for maximum accuracy.
    """
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline not initialized. Check your Groq API key.",
        )

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        result = rag.query(
            question=request.question,
            conversation_history=request.conversation_history,
            top_k=request.top_k,
            use_reranking=request.use_reranking,
        )
        return QueryResponse(**result)

    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/voice-query")
async def voice_query(file: UploadFile = File(...)):
    """
    Takes an audio file, transcribes it, runs a RAG query, and generates speech for the answer.
    """
    if rag is None or audio_svc is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    # Save incoming audio temporarily
    temp_input = os.path.join(audio_svc.audio_dir, f"in_{uuid.uuid4().hex[:8]}.webm")
    try:
        with open(temp_input, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 1. STT
        question = audio_svc.transcribe_audio(temp_input)
        if not question.strip():
            raise HTTPException(status_code=400, detail="Could not understand audio")

        # 2. RAG Query
        result = rag.query(
            question=question,
            conversation_history=None, # Voice typically acts as single-turn unless session ID provided
            top_k=5,
            use_reranking=True,
        )

        # 3. TTS
        audio_path = await audio_svc.generate_speech(result["answer"])
        audio_filename = os.path.basename(audio_path)

        return {
            "question": question,
            "answer": result["answer"],
            "sources": result["sources"],
            "context_chunks": result["context_chunks"],
            "audio_url": f"/audio/{audio_filename}",
        }

    except Exception as e:
        logger.error(f"Voice query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        audio_svc.clean_up(temp_input)

from fastapi.responses import FileResponse

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve generated audio files."""
    if not audio_svc:
        raise HTTPException(status_code=503, detail="Audio service not available")
    
    file_path = os.path.join(audio_svc.audio_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio not found")
        
    return FileResponse(file_path, media_type="audio/mpeg")


@app.post("/ingest-text")
async def ingest_text(request: IngestTextRequest):
    """Ingest raw text directly into the knowledge base."""
    if rag is None:
        raise HTTPException(
            status_code=503,
            detail="RAG pipeline not initialized.",
        )

    try:
        result = rag.ingest_text(
            text=request.text,
            source_name=request.source_name,
        )
        return {"status": "success", **result}

    except Exception as e:
        logger.error(f"Error ingesting text: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def list_documents():
    """List all ingested documents and stats."""
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG not initialized")

    return rag.get_stats()


@app.delete("/documents")
async def delete_documents(request: DeleteRequest):
    """Delete a specific document or clear all documents."""
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG not initialized")

    if request.clear_all:
        rag.clear_all()
        return {"status": "success", "message": "All documents cleared"}

    if request.source_name:
        count = rag.delete_document(request.source_name)
        return {
            "status": "success",
            "message": f"Deleted {count} chunks from '{request.source_name}'",
        }

    raise HTTPException(
        status_code=400,
        detail="Provide source_name or set clear_all=true",
    )


# ── Run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
