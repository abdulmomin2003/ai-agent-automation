-- ============================================================
-- AI Sales Agent Platform — Supabase PostgreSQL Schema
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Agents ────────────────────────────────────────────────────
-- Each row is an independent AI agent with its own config
CREATE TABLE IF NOT EXISTS agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  system_prompt TEXT NOT NULL DEFAULT 'You are a helpful AI assistant. Answer questions based on the provided knowledge base.',
  persona_name TEXT DEFAULT 'AI Agent',
  voice_id TEXT DEFAULT 'en-US-AriaNeural',

  -- Optional per-agent API key overrides (null = use global)
  groq_api_key TEXT,
  elevenlabs_api_key TEXT,

  -- Channel configuration
  twilio_phone_number TEXT,
  whatsapp_enabled BOOLEAN DEFAULT false,
  email_enabled BOOLEAN DEFAULT false,
  call_enabled BOOLEAN DEFAULT false,
  forward_phone_number TEXT,

  -- Metadata
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- ── Knowledge Documents ──────────────────────────────────────
-- Tracks documents uploaded to each agent's knowledge base
CREATE TABLE IF NOT EXISTS knowledge_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  file_type TEXT,
  file_size_bytes INTEGER,
  total_chunks INTEGER DEFAULT 0,
  status TEXT DEFAULT 'processing',  -- processing | ready | failed
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ── Conversations ────────────────────────────────────────────
-- Groups messages into sessions per agent
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'web',  -- web | voice | whatsapp | email
  caller_phone TEXT,
  caller_email TEXT,
  status TEXT DEFAULT 'active',  -- active | ended | forwarded
  summary TEXT,
  started_at TIMESTAMPTZ DEFAULT now(),
  ended_at TIMESTAMPTZ
);

-- ── Messages ─────────────────────────────────────────────────
-- Individual messages within a conversation
CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,          -- user | assistant | system
  content TEXT NOT NULL,
  sources TEXT[],              -- RAG source documents referenced
  audio_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ── Call Logs ────────────────────────────────────────────────
-- Telephony-specific logs
CREATE TABLE IF NOT EXISTS call_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  call_sid TEXT UNIQUE,
  direction TEXT,              -- inbound | outbound
  from_number TEXT,
  to_number TEXT,
  status TEXT,                 -- ringing | in-progress | completed | forwarded
  duration_seconds INTEGER,
  recording_url TEXT,
  transcript TEXT,
  forwarded_to TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_agent ON knowledge_documents(agent_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_agent ON call_logs(agent_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_sid ON call_logs(call_sid);

-- ── Updated-at trigger ───────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS agents_updated_at ON agents;
CREATE TRIGGER agents_updated_at
  BEFORE UPDATE ON agents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
