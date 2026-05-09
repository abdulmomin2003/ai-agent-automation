"""
Pydantic models for the AI Sales Agent Platform.

These models are used for API request/response validation and
database record serialization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Agent Models ──────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str = "You are a helpful AI assistant. Answer questions based on the provided knowledge base."
    persona_name: str = "AI Agent"
    voice_id: str = "en-US-AriaNeural"
    groq_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    whatsapp_enabled: bool = False
    email_enabled: bool = False
    call_enabled: bool = False
    forward_phone_number: Optional[str] = None
    notification_email: Optional[str] = None      # agent owner's email for summaries/alerts
    send_summary_emails: bool = True              # auto-send summary after each conversation


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    persona_name: Optional[str] = None
    voice_id: Optional[str] = None
    groq_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    whatsapp_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    call_enabled: Optional[bool] = None
    forward_phone_number: Optional[str] = None
    notification_email: Optional[str] = None
    send_summary_emails: Optional[bool] = None


class Agent(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    system_prompt: str
    persona_name: str
    voice_id: str
    groq_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    whatsapp_enabled: bool = False
    email_enabled: bool = False
    call_enabled: bool = False
    forward_phone_number: Optional[str] = None
    notification_email: Optional[str] = None
    send_summary_emails: bool = True
    created_at: datetime
    updated_at: datetime

    # Computed stats (populated by API)
    document_count: int = 0
    conversation_count: int = 0


# ── Knowledge Document Models ────────────────────────────────

class KnowledgeDocument(BaseModel):
    id: UUID
    agent_id: UUID
    filename: str
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    total_chunks: int = 0
    status: str = "processing"
    created_at: datetime


# ── Conversation Models ──────────────────────────────────────

class ConversationCreate(BaseModel):
    agent_id: UUID
    channel: str = "web"
    caller_phone: Optional[str] = None
    caller_email: Optional[str] = None


class Conversation(BaseModel):
    id: UUID
    agent_id: UUID
    channel: str
    caller_phone: Optional[str] = None
    caller_email: Optional[str] = None
    status: str = "active"
    summary: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    message_count: int = 0


# ── Message Models ────────────────────────────────────────────

class MessageCreate(BaseModel):
    conversation_id: UUID
    role: str
    content: str
    sources: Optional[list[str]] = None
    audio_url: Optional[str] = None


class Message(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    sources: Optional[list[str]] = None
    audio_url: Optional[str] = None
    created_at: datetime


# ── Call Log Models ───────────────────────────────────────────

class CallLog(BaseModel):
    id: UUID
    conversation_id: Optional[UUID] = None
    agent_id: UUID
    call_sid: Optional[str] = None
    direction: Optional[str] = None
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[int] = None
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    forwarded_to: Optional[str] = None
    created_at: datetime


# ── Chat Request Models ──────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None  # Resume existing conversation


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    conversation_id: str
    message_id: str
