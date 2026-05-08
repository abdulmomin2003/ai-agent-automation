"""
Agent Manager — orchestrates multiple independent AI agents.

Each agent has its own:
- RAG pipeline (isolated vector store)
- System prompt and persona
- Channel configuration (voice, WhatsApp, email)
- API keys (optional per-agent overrides)

Pipelines are lazily initialized and cached in memory.
"""

import logging
import os
from typing import Optional
from uuid import UUID

from config import settings
from rag_pipeline import RAGPipeline
from tts_service import TTSService
from email_service import EmailService
from db import database as db

logger = logging.getLogger(__name__)


class AgentManager:
    """
    Manages the lifecycle and resources of all AI agents.

    - Creates/loads agent configurations from the database
    - Lazily initializes RAG pipelines per agent (isolated vector stores)
    - Provides scoped query, upload, and channel operations
    """

    def __init__(self):
        self._pipelines: dict[str, RAGPipeline] = {}
        self._tts_services: dict[str, TTSService] = {}
        self.email_service = EmailService()

        # Initialize database schema on startup
        try:
            db.init_schema()
            logger.info("Database schema ready")
        except Exception as e:
            logger.error("Failed to initialize database schema: %s", e)

    # ── Pipeline Management ────────────────────────────────────

    def _get_pipeline(self, agent_id: str, agent_config: dict = None) -> RAGPipeline:
        """Get or create a RAG pipeline for an agent."""
        agent_key = str(agent_id)

        if agent_key not in self._pipelines:
            if agent_config is None:
                agent_config = db.get_agent(agent_id)
            if agent_config is None:
                raise ValueError(f"Agent {agent_id} not found")

            # Agent-specific API key or global fallback
            api_key = agent_config.get("groq_api_key") or settings.GROQ_API_KEY

            # Agent-specific vector store directory
            vector_dir = os.path.join(settings.VECTOR_STORE_DIR, agent_key)

            # Agent-specific system prompt
            system_prompt = agent_config.get("system_prompt", "")

            pipeline = RAGPipeline(
                api_key=api_key,
                vector_store_dir=vector_dir,
                system_prompt=system_prompt,
            )
            self._pipelines[agent_key] = pipeline
            logger.info("Initialized RAG pipeline for agent %s", agent_key)

        return self._pipelines[agent_key]

    def _get_tts(self, agent_config: dict) -> TTSService:
        """Get or create a TTS service for an agent."""
        agent_key = str(agent_config["id"])

        if agent_key not in self._tts_services:
            elevenlabs_key = (
                agent_config.get("elevenlabs_api_key")
                or getattr(settings, "ELEVENLABS_API_KEY", None)
            )
            self._tts_services[agent_key] = TTSService(elevenlabs_api_key=elevenlabs_key)

        return self._tts_services[agent_key]

    def invalidate_pipeline(self, agent_id: str):
        """Remove cached pipeline (e.g., after config change)."""
        agent_key = str(agent_id)
        self._pipelines.pop(agent_key, None)
        self._tts_services.pop(agent_key, None)

    # ── Agent CRUD ─────────────────────────────────────────────

    def create_agent(self, data: dict) -> dict:
        """Create a new agent."""
        agent = db.create_agent(data)
        logger.info("Created agent: %s (%s)", agent["name"], agent["id"])
        return agent

    def get_agent(self, agent_id: str) -> Optional[dict]:
        """Get agent by ID."""
        return db.get_agent(agent_id)

    def list_agents(self) -> list[dict]:
        """List all agents."""
        return db.list_agents()

    def update_agent(self, agent_id: str, data: dict) -> Optional[dict]:
        """Update agent configuration."""
        agent = db.update_agent(agent_id, data)
        if agent:
            self.invalidate_pipeline(agent_id)
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent and all associated data."""
        self.invalidate_pipeline(agent_id)

        # Clean up vector store files
        vector_dir = os.path.join(settings.VECTOR_STORE_DIR, str(agent_id))
        if os.path.exists(vector_dir):
            import shutil
            shutil.rmtree(vector_dir, ignore_errors=True)

        return db.delete_agent(agent_id)

    # ── Knowledge Base Operations ──────────────────────────────

    def upload_document(self, agent_id: str, file_path: str, filename: str,
                        file_type: str = None, file_size: int = None) -> dict:
        """Upload and ingest a document into an agent's knowledge base."""
        agent = db.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Record in database
        doc_record = db.create_knowledge_doc(
            agent_id=agent_id,
            filename=filename,
            file_type=file_type,
            file_size_bytes=file_size,
        )

        try:
            # Ingest into agent-specific RAG pipeline
            pipeline = self._get_pipeline(agent_id, agent)
            result = pipeline.ingest_document(file_path)

            # Update doc status
            db.update_knowledge_doc_status(
                doc_id=doc_record["id"],
                status="ready",
                total_chunks=result.get("total_chunks", 0),
            )

            return {**result, "document_id": str(doc_record["id"])}

        except Exception as e:
            db.update_knowledge_doc_status(doc_record["id"], "failed")
            raise

    def get_documents(self, agent_id: str) -> list[dict]:
        """List documents for an agent."""
        return db.list_knowledge_docs(agent_id)

    def delete_document(self, agent_id: str, doc_id: str) -> bool:
        """Delete a document from an agent's knowledge base."""
        doc = db.delete_knowledge_doc(doc_id)
        if doc:
            # Also remove from vector store
            try:
                pipeline = self._get_pipeline(agent_id)
                pipeline.delete_document(doc["filename"])
            except Exception as e:
                logger.warning("Failed to remove vectors for doc %s: %s", doc_id, e)
        return doc is not None

    # ── Chat Operations ────────────────────────────────────────

    def chat(self, agent_id: str, message: str,
             conversation_id: str = None, channel: str = "web",
             on_tool_call: callable = None) -> dict:
        """
        Send a message to an agent and get a response.

        Creates or resumes a conversation and persists all messages.
        """
        agent = db.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Create or get conversation
        if conversation_id:
            conversation = db.get_conversation(conversation_id)
            if not conversation:
                conversation = db.create_conversation(agent_id, channel)
        else:
            conversation = db.create_conversation(agent_id, channel)

        conv_id = str(conversation["id"])

        # Save user message
        user_msg = db.create_message(conv_id, "user", message)

        # Get conversation history
        history_rows = db.list_messages(conv_id, limit=20)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in history_rows[:-1]  # Exclude the message we just added (it's in the query)
        ]

        # Query RAG pipeline
        pipeline = self._get_pipeline(agent_id, agent)
        result = pipeline.query(
            question=message,
            conversation_history=history if history else None,
            top_k=5,
            use_reranking=True,
            on_tool_call=on_tool_call,
        )

        # Save assistant message
        ai_msg = db.create_message(
            conv_id, "assistant", result["answer"],
            sources=result.get("sources"),
        )

        return {
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "context_chunks": result.get("context_chunks", []),
            "conversation_id": conv_id,
            "message_id": str(ai_msg["id"]),
        }

    def log_chat_background(self, agent_id: str, user_message: str, ai_answer: str, 
                            sources: list, conversation_id: str, channel: str = "web"):
        """
        Silently log a conversation to the database. Used by fast voice streams
        to avoid blocking the LLM on DB roundtrips.
        """
        try:
            # Create or get conversation
            conversation = db.get_conversation(conversation_id)
            if not conversation:
                conversation = db.create_conversation(agent_id, channel)
            
            # Save user message
            db.create_message(conversation_id, "user", user_message)
            # Save assistant message
            db.create_message(conversation_id, "assistant", ai_answer, sources=sources)
        except Exception as e:
            logger.error(f"Failed to log chat in background: {e}")

    # ── Voice Operations ───────────────────────────────────────

    async def voice_query(self, agent_id: str, audio_path: str,
                          conversation_id: str = None,
                          on_tool_call: callable = None) -> dict:
        """
        Process a voice query: STT → RAG → TTS.

        Returns the answer text, audio URL, and transcription.
        """
        from audio_service import AudioService

        agent = db.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # STT
        audio_svc = AudioService(
            api_key=agent.get("groq_api_key") or settings.GROQ_API_KEY
        )
        question = audio_svc.transcribe_audio(audio_path)
        if not question.strip():
            raise ValueError("Could not understand audio")

        # RAG query with chat persistence
        result = self.chat(agent_id, question, conversation_id, channel="voice", on_tool_call=on_tool_call)

        # TTS
        tts = self._get_tts(agent)
        audio_file = await tts.generate_speech(
            result["answer"],
            voice_id=agent.get("voice_id", "en-US-AriaNeural"),
        )
        audio_filename = os.path.basename(audio_file)

        return {
            **result,
            "question": question,
            "audio_url": f"/audio/{audio_filename}",
        }

    # ── Conversation Management ────────────────────────────────

    def get_conversations(self, agent_id: str) -> list[dict]:
        """List conversations for an agent."""
        return db.list_conversations(agent_id)

    def get_messages(self, conversation_id: str) -> list[dict]:
        """Get messages for a conversation."""
        return db.list_messages(conversation_id)

    def get_call_logs(self, agent_id: str) -> list[dict]:
        """Get call logs for an agent."""
        return db.list_call_logs(agent_id)
