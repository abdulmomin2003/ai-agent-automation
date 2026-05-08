"""
Database connection and CRUD operations for Supabase PostgreSQL.

Uses psycopg3 for async-capable connection pooling.
All operations are agent-scoped for multi-tenancy.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from config import settings

logger = logging.getLogger(__name__)

# ── Connection Pool ───────────────────────────────────────────

_pool = None


def get_dsn() -> str:
    """Build connection DSN from settings."""
    return settings.postgres_dsn


def get_connection():
    """Get a database connection with dict row factory."""
    dsn = get_dsn()
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set DATABASE_URL or Supabase DB credentials in .env"
        )
    return psycopg.connect(dsn, row_factory=dict_row)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema Initialization ────────────────────────────────────

def init_schema():
    """Run schema.sql to create tables if they don't exist."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        logger.warning("schema.sql not found at %s", schema_path)
        return

    with open(schema_path, "r") as f:
        sql = f.read()

    try:
        with get_db() as conn:
            conn.execute(sql)
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize schema: %s", e)
        raise


# ── Agent CRUD ────────────────────────────────────────────────

def create_agent(data: dict) -> dict:
    """Create a new agent."""
    fields = [
        "name", "description", "system_prompt", "persona_name", "voice_id",
        "groq_api_key", "elevenlabs_api_key", "twilio_phone_number",
        "whatsapp_enabled", "email_enabled", "call_enabled", "forward_phone_number",
    ]
    present = {k: v for k, v in data.items() if k in fields and v is not None}
    columns = ", ".join(present.keys())
    placeholders = ", ".join(f"%({k})s" for k in present.keys())

    sql = f"""
        INSERT INTO agents ({columns})
        VALUES ({placeholders})
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(sql, present).fetchone()
    return dict(row)


def get_agent(agent_id: str | UUID) -> Optional[dict]:
    """Get a single agent by ID."""
    sql = "SELECT * FROM agents WHERE id = %s"
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id),)).fetchone()
    return dict(row) if row else None


def list_agents() -> list[dict]:
    """List all agents with document and conversation counts."""
    sql = """
        SELECT a.*,
               COALESCE(d.doc_count, 0) AS document_count,
               COALESCE(c.conv_count, 0) AS conversation_count
        FROM agents a
        LEFT JOIN (
            SELECT agent_id, COUNT(*) AS doc_count
            FROM knowledge_documents
            GROUP BY agent_id
        ) d ON d.agent_id = a.id
        LEFT JOIN (
            SELECT agent_id, COUNT(*) AS conv_count
            FROM conversations
            GROUP BY agent_id
        ) c ON c.agent_id = a.id
        ORDER BY a.created_at DESC
    """
    with get_db() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def update_agent(agent_id: str | UUID, data: dict) -> Optional[dict]:
    """Update an agent's configuration."""
    allowed = [
        "name", "description", "system_prompt", "persona_name", "voice_id",
        "groq_api_key", "elevenlabs_api_key", "twilio_phone_number",
        "whatsapp_enabled", "email_enabled", "call_enabled", "forward_phone_number",
    ]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return get_agent(agent_id)

    set_clause = ", ".join(f"{k} = %({k})s" for k in updates.keys())
    updates["id"] = str(agent_id)

    sql = f"UPDATE agents SET {set_clause} WHERE id = %(id)s RETURNING *"
    with get_db() as conn:
        row = conn.execute(sql, updates).fetchone()
    return dict(row) if row else None


def delete_agent(agent_id: str | UUID) -> bool:
    """Delete an agent and all associated data (cascades)."""
    sql = "DELETE FROM agents WHERE id = %s RETURNING id"
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id),)).fetchone()
    return row is not None


# ── Knowledge Document CRUD ───────────────────────────────────

def create_knowledge_doc(agent_id: str | UUID, filename: str,
                         file_type: str = None, file_size_bytes: int = None) -> dict:
    """Record a new knowledge document."""
    sql = """
        INSERT INTO knowledge_documents (agent_id, filename, file_type, file_size_bytes)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id), filename, file_type, file_size_bytes)).fetchone()
    return dict(row)


def update_knowledge_doc_status(doc_id: str | UUID, status: str,
                                total_chunks: int = None) -> None:
    """Update document processing status."""
    if total_chunks is not None:
        sql = "UPDATE knowledge_documents SET status = %s, total_chunks = %s WHERE id = %s"
        params = (status, total_chunks, str(doc_id))
    else:
        sql = "UPDATE knowledge_documents SET status = %s WHERE id = %s"
        params = (status, str(doc_id))

    with get_db() as conn:
        conn.execute(sql, params)


def list_knowledge_docs(agent_id: str | UUID) -> list[dict]:
    """List all documents for an agent."""
    sql = """
        SELECT * FROM knowledge_documents
        WHERE agent_id = %s
        ORDER BY created_at DESC
    """
    with get_db() as conn:
        rows = conn.execute(sql, (str(agent_id),)).fetchall()
    return [dict(r) for r in rows]


def delete_knowledge_doc(doc_id: str | UUID) -> Optional[dict]:
    """Delete a knowledge document record."""
    sql = "DELETE FROM knowledge_documents WHERE id = %s RETURNING *"
    with get_db() as conn:
        row = conn.execute(sql, (str(doc_id),)).fetchone()
    return dict(row) if row else None


# ── Conversation CRUD ─────────────────────────────────────────

def create_conversation(agent_id: str | UUID, channel: str = "web",
                        caller_phone: str = None, caller_email: str = None) -> dict:
    """Start a new conversation."""
    sql = """
        INSERT INTO conversations (agent_id, channel, caller_phone, caller_email)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id), channel, caller_phone, caller_email)).fetchone()
    return dict(row)


def get_conversation(conv_id: str | UUID) -> Optional[dict]:
    """Get a conversation by ID."""
    sql = "SELECT * FROM conversations WHERE id = %s"
    with get_db() as conn:
        row = conn.execute(sql, (str(conv_id),)).fetchone()
    return dict(row) if row else None


def list_conversations(agent_id: str | UUID, limit: int = 50) -> list[dict]:
    """List conversations for an agent with message counts."""
    sql = """
        SELECT c.*,
               COALESCE(m.msg_count, 0) AS message_count
        FROM conversations c
        LEFT JOIN (
            SELECT conversation_id, COUNT(*) AS msg_count
            FROM messages
            GROUP BY conversation_id
        ) m ON m.conversation_id = c.id
        WHERE c.agent_id = %s
        ORDER BY c.started_at DESC
        LIMIT %s
    """
    with get_db() as conn:
        rows = conn.execute(sql, (str(agent_id), limit)).fetchall()
    return [dict(r) for r in rows]


def end_conversation(conv_id: str | UUID, summary: str = None) -> None:
    """Mark a conversation as ended."""
    sql = "UPDATE conversations SET status = 'ended', ended_at = now(), summary = %s WHERE id = %s"
    with get_db() as conn:
        conn.execute(sql, (summary, str(conv_id)))


# ── Message CRUD ──────────────────────────────────────────────

def create_message(conversation_id: str | UUID, role: str, content: str,
                   sources: list[str] = None, audio_url: str = None) -> dict:
    """Add a message to a conversation."""
    sql = """
        INSERT INTO messages (conversation_id, role, content, sources, audio_url)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(
            sql,
            (str(conversation_id), role, content, sources, audio_url)
        ).fetchone()
    return dict(row)


def list_messages(conversation_id: str | UUID, limit: int = 100) -> list[dict]:
    """Get messages for a conversation in chronological order."""
    sql = """
        SELECT * FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        LIMIT %s
    """
    with get_db() as conn:
        rows = conn.execute(sql, (str(conversation_id), limit)).fetchall()
    return [dict(r) for r in rows]


# ── Call Log CRUD ─────────────────────────────────────────────

def create_call_log(agent_id: str | UUID, call_sid: str = None,
                    conversation_id: str | UUID = None,
                    direction: str = "inbound",
                    from_number: str = None, to_number: str = None) -> dict:
    """Create a call log entry."""
    sql = """
        INSERT INTO call_logs (agent_id, call_sid, conversation_id, direction, from_number, to_number, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'ringing')
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(
            sql,
            (str(agent_id), call_sid, str(conversation_id) if conversation_id else None,
             direction, from_number, to_number)
        ).fetchone()
    return dict(row)


def update_call_log(call_sid: str, **kwargs) -> None:
    """Update a call log by Twilio Call SID."""
    allowed = ["status", "duration_seconds", "recording_url", "transcript", "forwarded_to"]
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return

    set_clause = ", ".join(f"{k} = %({k})s" for k in updates.keys())
    updates["call_sid"] = call_sid

    sql = f"UPDATE call_logs SET {set_clause} WHERE call_sid = %(call_sid)s"
    with get_db() as conn:
        conn.execute(sql, updates)


def list_call_logs(agent_id: str | UUID, limit: int = 50) -> list[dict]:
    """List call logs for an agent."""
    sql = """
        SELECT * FROM call_logs
        WHERE agent_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """
    with get_db() as conn:
        rows = conn.execute(sql, (str(agent_id), limit)).fetchall()
    return [dict(r) for r in rows]
