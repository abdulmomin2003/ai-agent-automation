import axios from "axios";

// FastAPI backend URL
const getBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
};

const API_BASE_URL = getBaseUrl();

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

// ── Types ────────────────────────────────────────────────────

export interface Agent {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  persona_name: string;
  voice_id: string;
  groq_api_key: string | null;
  elevenlabs_api_key: string | null;
  twilio_phone_number: string | null;
  whatsapp_enabled: boolean;
  email_enabled: boolean;
  call_enabled: boolean;
  forward_phone_number: string | null;
  created_at: string;
  updated_at: string;
  document_count: number;
  conversation_count: number;
}

export interface AgentCreate {
  name: string;
  description?: string;
  system_prompt?: string;
  persona_name?: string;
  voice_id?: string;
  groq_api_key?: string;
  elevenlabs_api_key?: string;
  twilio_phone_number?: string;
  whatsapp_enabled?: boolean;
  email_enabled?: boolean;
  call_enabled?: boolean;
  forward_phone_number?: string;
}

export interface KnowledgeDocument {
  id: string;
  agent_id: string;
  filename: string;
  file_type: string | null;
  file_size_bytes: number | null;
  total_chunks: number;
  status: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  agent_id: string;
  channel: string;
  caller_phone: string | null;
  caller_email: string | null;
  status: string;
  summary: string | null;
  started_at: string;
  ended_at: string | null;
  message_count: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  sources: string[] | null;
  audio_url: string | null;
  created_at: string;
}

export interface ChatResponse {
  answer: string;
  sources: string[];
  context_chunks: Array<{ text: string; source: string; score: number }>;
  conversation_id: string;
  message_id: string;
}

export interface CallLog {
  id: string;
  conversation_id: string | null;
  agent_id: string;
  call_sid: string | null;
  direction: string | null;
  from_number: string | null;
  to_number: string | null;
  status: string | null;
  duration_seconds: number | null;
  recording_url: string | null;
  transcript: string | null;
  forwarded_to: string | null;
  created_at: string;
}

// ── API Methods ──────────────────────────────────────────────

export const api = {
  // Health
  checkHealth: async () => {
    const res = await apiClient.get("/health");
    return res.data;
  },

  // ── Agent CRUD ──────────────────────────────────────────
  createAgent: async (data: AgentCreate): Promise<Agent> => {
    const res = await apiClient.post("/agents", data);
    return res.data.agent;
  },

  listAgents: async (): Promise<Agent[]> => {
    const res = await apiClient.get("/agents");
    return res.data.agents;
  },

  getAgent: async (agentId: string): Promise<Agent> => {
    const res = await apiClient.get(`/agents/${agentId}`);
    return res.data.agent;
  },

  updateAgent: async (agentId: string, data: Partial<AgentCreate>): Promise<Agent> => {
    const res = await apiClient.put(`/agents/${agentId}`, data);
    return res.data.agent;
  },

  deleteAgent: async (agentId: string): Promise<void> => {
    await apiClient.delete(`/agents/${agentId}`);
  },

  // ── Knowledge Base ──────────────────────────────────────
  uploadDocument: async (agentId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await apiClient.post(`/agents/${agentId}/upload`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  listDocuments: async (agentId: string): Promise<KnowledgeDocument[]> => {
    const res = await apiClient.get(`/agents/${agentId}/documents`);
    return res.data.documents;
  },

  deleteDocument: async (agentId: string, docId: string) => {
    const res = await apiClient.delete(`/agents/${agentId}/documents/${docId}`);
    return res.data;
  },

  // ── Chat ────────────────────────────────────────────────
  chat: async (agentId: string, message: string, conversationId?: string): Promise<ChatResponse> => {
    const res = await apiClient.post(`/agents/${agentId}/chat`, {
      message,
      conversation_id: conversationId,
    });
    return res.data;
  },

  // ── Voice ───────────────────────────────────────────────
  voiceQuery: async (agentId: string, audioBlob: Blob): Promise<ChatResponse & { audio_url: string; question: string }> => {
    const formData = new FormData();
    formData.append("file", audioBlob, "voice.webm");
    const res = await apiClient.post(`/agents/${agentId}/voice-query`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  // ── Conversations ───────────────────────────────────────
  listConversations: async (agentId: string): Promise<Conversation[]> => {
    const res = await apiClient.get(`/agents/${agentId}/conversations`);
    return res.data.conversations;
  },

  getMessages: async (agentId: string, convId: string): Promise<Message[]> => {
    const res = await apiClient.get(`/agents/${agentId}/conversations/${convId}/messages`);
    return res.data.messages;
  },

  // ── Call Logs ───────────────────────────────────────────
  listCallLogs: async (agentId: string): Promise<CallLog[]> => {
    const res = await apiClient.get(`/agents/${agentId}/call-logs`);
    return res.data.call_logs;
  },

  // ── Audio ───────────────────────────────────────────────
  getAudioUrl: (filename: string): string => {
    return `${API_BASE_URL}/audio/${filename}`;
  },
};
