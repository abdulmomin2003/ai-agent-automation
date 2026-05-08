"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Plus, Bot, Phone, MessageSquare, Mail, FileText, ArrowRight,
  Sparkles, Loader2, Trash2, Settings, ChevronRight,
} from "lucide-react";
import { api, Agent } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      const data = await api.listAgents();
      setAgents(data);
    } catch (err) {
      console.error("Failed to load agents", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, agentId: string) => {
    e.stopPropagation();
    if (!confirm("Delete this agent? This will remove all conversations, documents, and settings.")) return;
    setDeleting(agentId);
    try {
      await api.deleteAgent(agentId);
      setAgents((prev) => prev.filter((a) => a.id !== agentId));
    } catch (err) {
      console.error("Failed to delete agent", err);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">AI Agent Platform</h1>
              <p className="text-xs text-muted-foreground">Multi-Agent Automation</p>
            </div>
          </div>
          <button
            onClick={() => router.push("/agents/new")}
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2.5 rounded-xl font-medium text-sm transition-all shadow-sm hover:shadow-md"
          >
            <Plus className="w-4 h-4" />
            New Agent
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <div className="max-w-7xl mx-auto px-6 pt-12 pb-8">
        <div className="flex flex-col items-center text-center mb-12">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-medium mb-4">
            <Sparkles className="w-3.5 h-3.5" />
            AI-Powered Sales Agents
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">
            Your <span className="gradient-text">Intelligent Agents</span>
          </h2>
          <p className="text-muted-foreground max-w-lg">
            Create AI agents for any business — law firms, plumbers, restaurants, clinics.
            Each agent has its own knowledge base, voice, and communication channels.
          </p>
        </div>

        {/* Agent Grid */}
        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center py-20">
            <div className="w-20 h-20 rounded-2xl bg-muted flex items-center justify-center mb-6">
              <Bot className="w-10 h-10 text-muted-foreground/40" />
            </div>
            <h3 className="text-xl font-semibold mb-2">No agents yet</h3>
            <p className="text-muted-foreground mb-6 text-center max-w-sm">
              Create your first AI agent to get started. Upload documents, configure voice settings, and start handling calls.
            </p>
            <button
              onClick={() => router.push("/agents/new")}
              className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-3 rounded-xl font-medium transition-all"
            >
              <Plus className="w-4 h-4" />
              Create Your First Agent
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {agents.map((agent) => (
              <div
                key={agent.id}
                onClick={() => router.push(`/agents/${agent.id}`)}
                className="group relative bg-card border border-border rounded-2xl p-6 cursor-pointer transition-all duration-300 hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 hover:-translate-y-0.5"
              >
                {/* Agent Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center">
                      <Bot className="w-6 h-6 text-primary" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-base">{agent.name}</h3>
                      <p className="text-xs text-muted-foreground">{agent.persona_name}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => handleDelete(e, agent.id)}
                      className="p-2 rounded-lg text-muted-foreground hover:text-danger hover:bg-danger/10 transition-all opacity-0 group-hover:opacity-100"
                    >
                      {deleting === agent.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Description */}
                {agent.description && (
                  <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                    {agent.description}
                  </p>
                )}

                {/* Stats */}
                <div className="flex items-center gap-4 mb-4 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5" />
                    <span>{agent.document_count} docs</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5" />
                    <span>{agent.conversation_count} chats</span>
                  </div>
                </div>

                {/* Channel Badges */}
                <div className="flex flex-wrap gap-2">
                  {agent.call_enabled && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-success/10 text-success text-xs font-medium">
                      <Phone className="w-3 h-3" /> Voice
                    </span>
                  )}
                  {agent.whatsapp_enabled && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-success/10 text-success text-xs font-medium">
                      <MessageSquare className="w-3 h-3" /> WhatsApp
                    </span>
                  )}
                  {agent.email_enabled && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary/10 text-primary text-xs font-medium">
                      <Mail className="w-3 h-3" /> Email
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-muted text-muted-foreground text-xs font-medium">
                    <MessageSquare className="w-3 h-3" /> Web Chat
                  </span>
                </div>

                {/* Arrow indicator */}
                <div className="absolute right-4 bottom-6 opacity-0 group-hover:opacity-100 transition-all translate-x-1 group-hover:translate-x-0">
                  <ChevronRight className="w-5 h-5 text-primary" />
                </div>
              </div>
            ))}

            {/* New Agent Card */}
            <div
              onClick={() => router.push("/agents/new")}
              className="border-2 border-dashed border-border rounded-2xl p-6 flex flex-col items-center justify-center cursor-pointer transition-all hover:border-primary/40 hover:bg-primary/5 min-h-[220px]"
            >
              <div className="w-14 h-14 rounded-xl bg-muted flex items-center justify-center mb-4">
                <Plus className="w-7 h-7 text-muted-foreground" />
              </div>
              <p className="font-medium text-sm mb-1">Create New Agent</p>
              <p className="text-xs text-muted-foreground text-center">
                Law firm, plumber, clinic, restaurant...
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
