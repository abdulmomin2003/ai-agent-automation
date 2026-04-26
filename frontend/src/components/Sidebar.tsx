"use client";

import { useState, useRef, useEffect } from "react";
import { Upload, FileText, Trash2, Loader2, Database, AlertCircle } from "lucide-react";
import { api, DocumentStats } from "@/lib/api";

export default function Sidebar() {
  const [stats, setStats] = useState<DocumentStats | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchStats = async () => {
    try {
      const data = await api.getDocuments();
      setStats(data);
    } catch (err) {
      console.error("Failed to fetch documents", err);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setError("");

    try {
      await api.uploadDocument(file);
      await fetchStats();
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Upload failed");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (source: string) => {
    try {
      await api.deleteDocument(source);
      await fetchStats();
    } catch (err) {
      console.error("Failed to delete document", err);
    }
  };

  return (
    <div className="w-72 bg-card border-r border-border h-full flex flex-col p-4 shrink-0">
      <div className="flex items-center gap-2 px-2 py-4 mb-6">
        <div className="bg-primary/20 p-2 rounded-lg">
          <Database className="w-5 h-5 text-primary" />
        </div>
        <h1 className="font-semibold text-lg tracking-tight">Knowledge Base</h1>
      </div>

      <div className="mb-6 px-2">
        <input
          type="file"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileUpload}
          accept=".pdf,.docx,.txt,.md,.xlsx,.csv"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground font-medium py-2.5 rounded-xl transition-all shadow-sm disabled:opacity-50"
        >
          {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {isUploading ? "Uploading..." : "Upload Document"}
        </button>
        {error && (
          <div className="mt-3 flex items-start gap-2 text-red-400 text-xs bg-red-400/10 p-2 rounded-lg border border-red-400/20">
            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <p>{error}</p>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          Documents ({stats?.unique_documents || 0})
        </div>

        {stats?.sources.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground/60 flex flex-col items-center">
            <FileText className="w-8 h-8 mb-2 opacity-20" />
            <p className="text-sm">No documents yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {stats?.sources.map((source) => (
              <div
                key={source}
                className="group flex items-center justify-between p-3 rounded-xl bg-muted/30 border border-transparent hover:border-border hover:bg-muted/50 transition-all"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <FileText className="w-4 h-4 text-primary shrink-0" />
                  <span className="text-sm truncate" title={source}>
                    {source}
                  </span>
                </div>
                <button
                  onClick={() => handleDelete(source)}
                  className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/20 hover:text-red-400 rounded-md transition-all shrink-0 text-muted-foreground"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-auto pt-4 px-2 border-t border-border/50">
        <div className="flex justify-between items-center text-xs text-muted-foreground">
          <span>Vector Chunks</span>
          <span className="font-medium px-2 py-1 bg-muted rounded-md">{stats?.total_chunks || 0}</span>
        </div>
      </div>
    </div>
  );
}
