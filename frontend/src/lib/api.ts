import axios from "axios";

// Fast API backend URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export interface QueryResponse {
  answer: string;
  sources: string[];
  context_chunks: Array<{ text: string; source: string; score: number }>;
}

export interface DocumentStats {
  total_chunks: number;
  unique_documents: number;
  sources: string[];
}

export const api = {
  // Health Check
  checkHealth: async () => {
    const res = await apiClient.get("/health");
    return res.data;
  },

  // Document Management
  getDocuments: async (): Promise<DocumentStats> => {
    const res = await apiClient.get("/documents");
    return res.data;
  },

  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await apiClient.post("/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  deleteDocument: async (source_name: string) => {
    const res = await apiClient.delete("/documents", {
      data: { source_name },
    });
    return res.data;
  },

  // Query / Chat
  query: async (question: string, history?: { role: string; content: string }[]): Promise<QueryResponse> => {
    const res = await apiClient.post("/query", {
      question,
      conversation_history: history,
      top_k: 5,
      use_reranking: true,
    });
    return res.data;
  },
};
