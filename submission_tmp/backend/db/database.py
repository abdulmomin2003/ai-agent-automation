"""
Database connection and CRUD operations for Supabase PostgreSQL.

Uses psycopg3 for async-capable connection pooling.
All operations are agent-scoped for multi-tenancy.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import date, time, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from config import settings

logger = logging.getLogger(__name__)

# ── Connection Pool ───────────────────────────────────────────

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
        "notification_email", "send_summary_emails",
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
        "notification_email", "send_summary_emails",
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
                        caller_phone: str = None, caller_email: str = None,
                        conversation_id: str | UUID = None) -> dict:
    """Start a new conversation."""
    if conversation_id:
        sql = """
            INSERT INTO conversations (id, agent_id, channel, caller_phone, caller_email)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """
        params = (str(conversation_id), str(agent_id), channel, caller_phone, caller_email)
    else:
        sql = """
            INSERT INTO conversations (agent_id, channel, caller_phone, caller_email)
            VALUES (%s, %s, %s, %s)
            RETURNING *
        """
        params = (str(agent_id), channel, caller_phone, caller_email)

    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
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
    """Mark a conversation as ended with optional summary."""
    sql = "UPDATE conversations SET status = 'ended', ended_at = now(), summary = %s WHERE id = %s"
    with get_db() as conn:
        conn.execute(sql, (summary, str(conv_id)))


def update_conversation_summary(conv_id: str | UUID, summary: str) -> None:
    """Update only the summary field of a conversation."""
    sql = "UPDATE conversations SET summary = %s WHERE id = %s"
    with get_db() as conn:
        conn.execute(sql, (summary, str(conv_id)))


def update_conversation_email(conv_id: str | UUID, caller_email: str) -> None:
    """Update the caller email on a conversation."""
    sql = "UPDATE conversations SET caller_email = %s WHERE id = %s"
    with get_db() as conn:
        conn.execute(sql, (caller_email, str(conv_id)))


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


# ── Dynamic Agent Tools ───────────────────────────────────────

def get_agent_tools(agent_id: str | UUID) -> list[dict]:
    """Get all custom tools for an agent."""
    sql = "SELECT * FROM agent_tools WHERE agent_id = %s ORDER BY created_at ASC"
    with get_db() as conn:
        rows = conn.execute(sql, (str(agent_id),)).fetchall()
    return [dict(r) for r in rows]


def create_agent_tool(agent_id: str | UUID, data: dict) -> dict:
    """Create a new custom tool for an agent."""
    sql = """
        INSERT INTO agent_tools (agent_id, name, description, method, webhook_url, parameters_schema)
        VALUES (%(agent_id)s, %(name)s, %(description)s, %(method)s, %(webhook_url)s, %(parameters_schema)s)
        RETURNING *
    """
    params = {
        "agent_id": str(agent_id),
        "name": data["name"],
        "description": data["description"],
        "method": data.get("method", "POST"),
        "webhook_url": data["webhook_url"],
        "parameters_schema": json.dumps(data.get("parameters_schema", {}))
    }
    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row)


def delete_agent_tool(tool_id: str | UUID) -> bool:
    """Delete a custom tool."""
    sql = "DELETE FROM agent_tools WHERE id = %s RETURNING id"
    with get_db() as conn:
        row = conn.execute(sql, (str(tool_id),)).fetchone()
    return row is not None


# ── Bookings ──────────────────────────────────────────────────

def get_bookings(agent_id: str | UUID, date_str: str = None, status: str = None) -> list[dict]:
    """Get bookings for an agent, optionally filtered by date and/or status."""
    conditions = ["agent_id = %s"]
    params: list = [str(agent_id)]

    if date_str:
        conditions.append("booking_date = %s")
        params.append(date_str)
    if status:
        conditions.append("status = %s")
        params.append(status)

    sql = f"""
        SELECT * FROM bookings
        WHERE {' AND '.join(conditions)}
        ORDER BY booking_date ASC, booking_time ASC
    """
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # Serialize date/time objects to strings
        if isinstance(d.get("booking_date"), date):
            d["booking_date"] = d["booking_date"].isoformat()
        if isinstance(d.get("booking_time"), (time, timedelta)):
            d["booking_time"] = str(d["booking_time"])[:5]  # HH:MM
        result.append(d)
    return result


def get_booking_by_id(booking_id: str | UUID) -> Optional[dict]:
    """Get a single booking by ID."""
    sql = "SELECT * FROM bookings WHERE id = %s"
    with get_db() as conn:
        row = conn.execute(sql, (str(booking_id),)).fetchone()
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("booking_date"), date):
        d["booking_date"] = d["booking_date"].isoformat()
    if isinstance(d.get("booking_time"), (time, timedelta)):
        d["booking_time"] = str(d["booking_time"])[:5]
    return d


def create_booking(agent_id: str | UUID, data: dict) -> dict:
    """Create a booking for an agent."""
    sql = """
        INSERT INTO bookings (agent_id, customer_name, customer_phone, customer_email, booking_date, booking_time, duration_minutes, notes, status)
        VALUES (%(agent_id)s, %(customer_name)s, %(customer_phone)s, %(customer_email)s,
                %(booking_date)s, %(booking_time)s, %(duration_minutes)s, %(notes)s, %(status)s)
        RETURNING *
    """
    params = {
        "agent_id": str(agent_id),
        "customer_name": data.get("customer_name"),
        "customer_phone": data.get("customer_phone"),
        "customer_email": data.get("customer_email"),
        "booking_date": data["booking_date"],
        "booking_time": data["booking_time"],
        "duration_minutes": data.get("duration_minutes", 60),
        "notes": data.get("notes"),
        "status": data.get("status", "confirmed"),
    }
    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
    d = dict(row)
    if isinstance(d.get("booking_date"), date):
        d["booking_date"] = d["booking_date"].isoformat()
    if isinstance(d.get("booking_time"), (time, timedelta)):
        d["booking_time"] = str(d["booking_time"])[:5]
    return d


def update_booking_status(booking_id: str | UUID, status: str, email_sent: bool = None) -> Optional[dict]:
    """Update the status of a booking."""
    if email_sent is not None:
        sql = "UPDATE bookings SET status = %s, email_sent = %s WHERE id = %s RETURNING *"
        params = (status, email_sent, str(booking_id))
    else:
        sql = "UPDATE bookings SET status = %s WHERE id = %s RETURNING *"
        params = (status, str(booking_id))

    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("booking_date"), date):
        d["booking_date"] = d["booking_date"].isoformat()
    if isinstance(d.get("booking_time"), (time, timedelta)):
        d["booking_time"] = str(d["booking_time"])[:5]
    return d


def mark_booking_email_sent(booking_id: str | UUID) -> None:
    """Mark that a confirmation email was sent for this booking."""
    sql = "UPDATE bookings SET email_sent = true WHERE id = %s"
    with get_db() as conn:
        conn.execute(sql, (str(booking_id),))


# ── Availability Config ───────────────────────────────────────

def get_availability_config(agent_id: str | UUID) -> list[dict]:
    """Get weekly availability config for an agent."""
    sql = """
        SELECT * FROM availability_config
        WHERE agent_id = %s
        ORDER BY day_of_week ASC
    """
    with get_db() as conn:
        rows = conn.execute(sql, (str(agent_id),)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("start_time"), (time, timedelta)):
            d["start_time"] = str(d["start_time"])[:5]
        if isinstance(d.get("end_time"), (time, timedelta)):
            d["end_time"] = str(d["end_time"])[:5]
        result.append(d)
    return result


def upsert_availability_config(agent_id: str | UUID, day_of_week: int,
                                start_time: str, end_time: str,
                                slot_duration_minutes: int = 60,
                                is_active: bool = True) -> dict:
    """Create or update the availability config for a specific day."""
    sql = """
        INSERT INTO availability_config (agent_id, day_of_week, start_time, end_time, slot_duration_minutes, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (agent_id, day_of_week)
        DO UPDATE SET start_time = EXCLUDED.start_time,
                      end_time = EXCLUDED.end_time,
                      slot_duration_minutes = EXCLUDED.slot_duration_minutes,
                      is_active = EXCLUDED.is_active
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id), day_of_week, start_time, end_time, slot_duration_minutes, is_active)).fetchone()
    d = dict(row)
    if isinstance(d.get("start_time"), (time, timedelta)):
        d["start_time"] = str(d["start_time"])[:5]
    if isinstance(d.get("end_time"), (time, timedelta)):
        d["end_time"] = str(d["end_time"])[:5]
    return d


def set_default_availability(agent_id: str | UUID) -> None:
    """Set sensible default working hours (Mon-Fri, 9AM-5PM, 1-hour slots)."""
    defaults = [
        (0, "09:00", "17:00"),  # Monday
        (1, "09:00", "17:00"),  # Tuesday
        (2, "09:00", "17:00"),  # Wednesday
        (3, "09:00", "17:00"),  # Thursday
        (4, "09:00", "17:00"),  # Friday
        (5, "10:00", "14:00"),  # Saturday (half day)
        (6, "00:00", "00:00"),  # Sunday (closed, is_active=False)
    ]
    for i, (dow, start, end) in enumerate(defaults):
        upsert_availability_config(
            agent_id, dow, start, end,
            slot_duration_minutes=60,
            is_active=(i < 6),  # Sunday not active
        )


def get_blocked_slots(agent_id: str | UUID, date_str: str) -> list[dict]:
    """Get blocked slots for a specific date."""
    sql = """
        SELECT * FROM blocked_slots
        WHERE agent_id = %s AND blocked_date = %s
        ORDER BY start_time ASC NULLS FIRST
    """
    with get_db() as conn:
        rows = conn.execute(sql, (str(agent_id), date_str)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("start_time"), (time, timedelta)):
            d["start_time"] = str(d["start_time"])[:5]
        if isinstance(d.get("end_time"), (time, timedelta)):
            d["end_time"] = str(d["end_time"])[:5]
        if isinstance(d.get("blocked_date"), date):
            d["blocked_date"] = d["blocked_date"].isoformat()
        result.append(d)
    return result


def add_blocked_slot(agent_id: str | UUID, date_str: str,
                     start_time: str = None, end_time: str = None,
                     reason: str = None) -> dict:
    """Add a blocked slot for a specific date."""
    sql = """
        INSERT INTO blocked_slots (agent_id, blocked_date, start_time, end_time, reason)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
    """
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id), date_str, start_time, end_time, reason)).fetchone()
    return dict(row)


def compute_available_slots(agent_id: str | UUID, date_str: str) -> list[str]:
    """
    Compute available time slots for an agent on a given date.
    Returns list of 'HH:MM' strings for available slots.
    """
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return []

    # 0=Monday … 6=Sunday (Python weekday())
    day_of_week = target_date.weekday()

    # Get availability config for this day
    sql = """
        SELECT * FROM availability_config
        WHERE agent_id = %s AND day_of_week = %s AND is_active = true
    """
    with get_db() as conn:
        row = conn.execute(sql, (str(agent_id), day_of_week)).fetchone()

    if not row:
        return []  # Not a working day

    config = dict(row)
    start_t = config["start_time"]
    end_t = config["end_time"]
    duration = int(config.get("slot_duration_minutes") or 60)

    # Normalize time values
    def to_time(t):
        if isinstance(t, timedelta):
            total = int(t.total_seconds())
            return time(total // 3600, (total % 3600) // 60)
        if isinstance(t, time):
            return t
        if isinstance(t, str):
            parts = t.split(":")
            return time(int(parts[0]), int(parts[1]))
        return time(9, 0)

    start_t = to_time(start_t)
    end_t = to_time(end_t)

    # Generate all possible slots
    all_slots = []
    current = datetime.combine(target_date, start_t)
    end_dt = datetime.combine(target_date, end_t)
    while current < end_dt:
        slot_end = current + timedelta(minutes=duration)
        if slot_end <= end_dt:
            all_slots.append(current.strftime("%H:%M"))
        current = slot_end

    # Remove blocked slots (full day blocks)
    blocked = get_blocked_slots(agent_id, date_str)
    for block in blocked:
        if block.get("start_time") is None:
            # Full day blocked
            return []
        # Partial block — remove overlapping slots
        b_start = block.get("start_time", "00:00")
        b_end = block.get("end_time", "23:59")
        all_slots = [s for s in all_slots if not (b_start <= s < b_end)]

    # Remove already-booked slots
    existing = get_bookings(agent_id, date_str, status="confirmed")
    booked_times = {b["booking_time"][:5] for b in existing}
    available = [s for s in all_slots if s not in booked_times]

    return available
