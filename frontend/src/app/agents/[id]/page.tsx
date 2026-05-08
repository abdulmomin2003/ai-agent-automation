"use client";

import { useState, useEffect, useRef, use } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, Send, Bot, User, Loader2, Sparkles, FileText, Mic, Square,
  Upload, Trash2, Phone, MessageSquare, Mail, Settings, ChevronDown,
  ChevronUp, Clock, AlertCircle, Check, X, Save, PhoneCall, PhoneOff
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, Agent, KnowledgeDocument, Conversation, Message as ApiMessage, CallLog, ChatResponse, AgentCreate } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "chat" | "knowledge" | "conversations" | "calls" | "settings";

type ChatMsg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  audio_url?: string;
};

export default function AgentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: agentId } = use(params);
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [tab, setTab] = useState<Tab>("chat");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAgent(agentId).then(setAgent).catch(() => router.push("/")).finally(() => setLoading(false));
  }, [agentId, router]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;
  if (!agent) return null;

  const tabs: { id: Tab; label: string; icon: any }[] = [
    { id: "chat", label: "Chat", icon: MessageSquare },
    { id: "knowledge", label: "Knowledge Base", icon: FileText },
    { id: "conversations", label: "Conversations", icon: Clock },
    { id: "calls", label: "Call Logs", icon: Phone },
    { id: "settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border bg-card/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => router.push("/")} className="p-2 rounded-lg hover:bg-muted transition-colors">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary/20 to-accent/20 flex items-center justify-center">
              <Bot className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="font-semibold text-sm">{agent.name}</h1>
              <p className="text-xs text-muted-foreground">{agent.persona_name}</p>
            </div>
          </div>
          <div className="flex gap-1 bg-muted rounded-xl p-1">
            {tabs.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)} className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === t.id ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}>
                <t.icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="flex-1 max-w-7xl mx-auto w-full">
        {tab === "chat" && <ChatTab agentId={agentId} agent={agent} />}
        {tab === "knowledge" && <KnowledgeTab agentId={agentId} />}
        {tab === "conversations" && <ConversationsTab agentId={agentId} />}
        {tab === "calls" && <CallsTab agentId={agentId} />}
        {tab === "settings" && <SettingsTab agent={agent} onUpdate={setAgent} />}
      </div>
    </div>
  );
}

/* ═══ CHAT TAB ═══ */
function ChatTab({ agentId, agent }: { agentId: string; agent: Agent }) {
  const [messages, setMessages] = useState<ChatMsg[]>([
    { id: "1", role: "assistant", content: `Hello! I'm ${agent.persona_name}. How can I help you today?` },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [convId, setConvId] = useState<string | undefined>();
  const [isRecording, setIsRecording] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, isLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    const text = input.trim();
    setMessages(p => [...p, { id: Date.now().toString(), role: "user", content: text }]);
    setInput("");
    setIsLoading(true);
    try {
      const res = await api.chat(agentId, text, convId);
      setConvId(res.conversation_id);
      setMessages(p => [...p, { id: res.message_id, role: "assistant", content: res.answer, sources: res.sources }]);
    } catch {
      setMessages(p => [...p, { id: Date.now().toString(), role: "assistant", content: "Sorry, I encountered an error." }]);
    } finally { setIsLoading(false); }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setIsLoading(true);
        try {
          const res = await api.voiceQuery(agentId, blob);
          setMessages(p => [...p, { id: Date.now().toString(), role: "user", content: res.question }]);
          setMessages(p => [...p, { id: (Date.now()+1).toString(), role: "assistant", content: res.answer, sources: res.sources, audio_url: res.audio_url }]);
          if (res.audio_url) { const a = new Audio(api.getAudioUrl(res.audio_url.replace("/audio/",""))); a.play().catch(()=>{}); }
        } catch { setMessages(p => [...p, { id: Date.now().toString(), role: "assistant", content: "Sorry, I had trouble processing your voice." }]); }
        finally { setIsLoading(false); stream.getTracks().forEach(t => t.stop()); }
      };
      mr.start();
      setIsRecording(true);
    } catch { alert("Please allow microphone access."); }
  };

  const stopRecording = () => { if (mediaRef.current && isRecording) { mediaRef.current.stop(); setIsRecording(false); } };

  const [showCallModal, setShowCallModal] = useState(false);

  return (
    <div className="flex flex-col h-[calc(100vh-57px)] relative">
      {/* Call Button Header */}
      <div className="flex justify-end p-4 pb-0">
        <button 
          onClick={() => setShowCallModal(true)}
          className="flex items-center gap-2 bg-primary/10 text-primary hover:bg-primary/20 px-4 py-2 rounded-xl font-medium transition-all"
        >
          <PhoneCall className="w-4 h-4" />
          Call Agent
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 sm:p-6 pb-48">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map(m => (
            <div key={m.id} className={cn("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")}>
              {m.role === "assistant" && <div className="w-8 h-8 shrink-0 rounded-full bg-primary/20 flex items-center justify-center mt-1"><Bot className="w-4 h-4 text-primary" /></div>}
              <div className={cn("px-4 py-3 text-sm max-w-[80%] rounded-2xl", m.role === "user" ? "bg-primary text-primary-foreground rounded-tr-sm" : "bg-card border border-border rounded-tl-sm")}>
                <div className={cn("prose prose-sm max-w-none break-words", m.role === "user" ? "prose-invert" : "dark:prose-invert")}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
                {m.sources && m.sources.length > 0 && <div className="mt-2 pt-2 border-t border-border/50 flex flex-wrap gap-1">{m.sources.map((s,i) => <span key={i} className="text-[10px] px-2 py-0.5 bg-muted rounded-md">{s}</span>)}</div>}
              </div>
              {m.role === "user" && <div className="w-8 h-8 shrink-0 rounded-full bg-muted flex items-center justify-center mt-1"><User className="w-4 h-4 text-muted-foreground" /></div>}
            </div>
          ))}
          {isLoading && <div className="flex gap-3"><div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center"><Loader2 className="w-4 h-4 text-primary animate-spin" /></div><div className="px-4 py-3 bg-card border border-border rounded-2xl rounded-tl-sm flex gap-1"><div className="w-2 h-2 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.3s]"/><div className="w-2 h-2 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.15s]"/><div className="w-2 h-2 rounded-full bg-primary/40 animate-bounce"/></div></div>}
          <div ref={endRef} />
        </div>
      </div>
      <div className="absolute bottom-0 inset-x-0 p-4 bg-gradient-to-t from-background via-background to-transparent pt-10">
        <div className="max-w-3xl mx-auto">
          <form onSubmit={handleSubmit} className={cn("relative flex items-end gap-2 bg-card border rounded-2xl p-2 shadow-sm transition-all", isRecording ? "border-red-500/50 ring-2 ring-red-500/20" : "border-border focus-within:ring-2 focus-within:ring-primary/20")}>
            <textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e); }}} placeholder={isRecording ? "Listening..." : "Ask a question..."} disabled={isRecording} className="flex-1 max-h-40 min-h-[44px] bg-transparent resize-none outline-none py-3 px-3 text-sm disabled:opacity-50" rows={1} />
            <div className="flex items-center gap-1 mb-0.5 mr-0.5">
              {isRecording ? <button type="button" onClick={stopRecording} className="w-11 h-11 shrink-0 bg-red-500 hover:bg-red-600 text-white rounded-xl flex items-center justify-center animate-pulse"><Square className="w-4 h-4 fill-current" /></button> : <button type="button" onClick={startRecording} disabled={isLoading} className="w-11 h-11 shrink-0 bg-muted hover:bg-muted/80 rounded-xl flex items-center justify-center disabled:opacity-50"><Mic className="w-5 h-5" /></button>}
              <button type="submit" disabled={!input.trim() || isLoading || isRecording} className="w-11 h-11 shrink-0 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl flex items-center justify-center disabled:opacity-50"><Send className="w-5 h-5" /></button>
            </div>
          </form>
        </div>
      </div>

      {showCallModal && (
        <CallSimulationModal 
          agent={agent} 
          agentId={agentId} 
          onClose={() => setShowCallModal(false)} 
        />
      )}
    </div>
  );
}

/* ═══ CALL SIMULATION MODAL ═══ */
function CallSimulationModal({ agent, agentId, onClose }: { agent: Agent, agentId: string, onClose: () => void }) {
  const [status, setStatus] = useState<"connecting" | "listening" | "processing" | "speaking" | "error">("connecting");
  const [transcript, setTranscript] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioQueue = useRef<Blob[]>([]);
  const isPlaying = useRef(false);
  const currentAudio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let mounted = true;
    const startCall = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (!mounted) { stream.getTracks().forEach(t => t.stop()); return; }
        streamRef.current = stream;

        // Ensure absolute URL
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws") || `${protocol}//${window.location.hostname}:8000`;
        const convId = crypto.randomUUID();
        const ws = new WebSocket(`${wsUrl}/web/voice/stream/${agentId}/${convId}`);
        wsRef.current = ws;

        ws.onopen = () => {
          setStatus("listening");
          
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
          audioCtxRef.current = audioCtx;
          const source = audioCtx.createMediaStreamSource(stream);
          const processor = audioCtx.createScriptProcessor(4096, 1, 1);

          processor.onaudioprocess = (e) => {
            if (ws.readyState === WebSocket.OPEN) {
              const inputData = e.inputBuffer.getChannelData(0);
              const pcm16 = new Int16Array(inputData.length);
              for (let i = 0; i < inputData.length; i++) {
                pcm16[i] = inputData[i] * 0x7FFF; // Convert Float32 to Int16
              }
              ws.send(pcm16.buffer);
            }
          };

          source.connect(processor);
          processor.connect(audioCtx.destination);
        };

        ws.onmessage = async (e) => {
          if (typeof e.data === "string") {
            const msg = JSON.parse(e.data);
            if (msg.type === "transcription") setTranscript(msg.text);
            if (msg.type === "audio_start") setStatus("speaking");
            if (msg.type === "ready") setStatus("listening");
            if (msg.type === "interrupt") {
              // Agent was interrupted by user speech
              audioQueue.current = [];
              isPlaying.current = false;
              if (currentAudio.current) {
                currentAudio.current.pause();
                currentAudio.current = null;
              }
              setStatus("listening");
            }
          } else {
            // It's binary audio data
            playAudioData(e.data);
          }
        };

        ws.onerror = () => setStatus("error");
        ws.onclose = () => { if(mounted) setStatus("error"); };

      } catch (err) {
        setStatus("error");
      }
    };

    startCall();

    return () => {
      mounted = false;
      if (wsRef.current) wsRef.current.close();
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (audioCtxRef.current) audioCtxRef.current.close();
    };
  }, [agentId]);

  const playAudioData = async (blob: Blob) => {
    audioQueue.current.push(blob);
    if (!isPlaying.current) playNextInQueue();
  };

  const playNextInQueue = async () => {
    if (audioQueue.current.length === 0) {
      isPlaying.current = false;
      setStatus("listening");
      return;
    }
    isPlaying.current = true;
    const blob = audioQueue.current.shift()!;
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio.current = audio;
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (currentAudio.current === audio) currentAudio.current = null;
      playNextInQueue();
    };
    audio.play().catch(() => playNextInQueue());
  };

  return (
    <div className="absolute inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-card border border-border shadow-2xl rounded-3xl p-8 w-full max-w-sm flex flex-col items-center text-center">
        <div className="w-24 h-24 rounded-full bg-primary/10 flex items-center justify-center relative mb-6">
          {status === "listening" && <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping opacity-50" />}
          {status === "speaking" && <div className="absolute inset-0 rounded-full bg-primary/30 animate-pulse" />}
          <Bot className={cn("w-10 h-10", status === "speaking" ? "text-primary" : "text-muted-foreground")} />
        </div>
        
        <h3 className="text-xl font-bold mb-1">{agent.persona_name || agent.name}</h3>
        <p className="text-sm text-muted-foreground capitalize mb-8 flex items-center gap-2">
          {status === "connecting" && <><Loader2 className="w-3 h-3 animate-spin"/> Connecting...</>}
          {status === "listening" && "Listening..."}
          {status === "speaking" && "Speaking..."}
          {status === "error" && "Call Failed"}
        </p>

        {transcript && (
          <div className="bg-muted p-4 rounded-xl w-full mb-8 max-h-32 overflow-y-auto text-sm italic">
            "{transcript}"
          </div>
        )}

        <button 
          onClick={onClose}
          className="w-16 h-16 rounded-full bg-red-500 hover:bg-red-600 text-white flex items-center justify-center transition-colors shadow-lg shadow-red-500/20"
        >
          <PhoneOff className="w-6 h-6" />
        </button>
      </div>
    </div>
  );
}

/* ═══ KNOWLEDGE TAB ═══ */
function KnowledgeTab({ agentId }: { agentId: string }) {
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.listDocuments(agentId).then(setDocs).catch(console.error);
  useEffect(() => { load(); }, [agentId]);

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    setUploading(true); setError("");
    try { await api.uploadDocument(agentId, f); await load(); if (fileRef.current) fileRef.current.value = ""; }
    catch (err: any) { setError(err.response?.data?.detail || "Upload failed"); }
    finally { setUploading(false); }
  };

  const del = async (docId: string) => { try { await api.deleteDocument(agentId, docId); await load(); } catch { } };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Knowledge Base</h2>
        <div>
          <input type="file" className="hidden" ref={fileRef} onChange={upload} accept=".pdf,.docx,.txt,.md,.xlsx,.csv,.pptx,.html,.json" />
          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50">
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {uploading ? "Uploading..." : "Upload Document"}
          </button>
        </div>
      </div>
      {error && <div className="mb-4 flex items-center gap-2 text-red-400 text-sm bg-red-400/10 p-3 rounded-xl border border-red-400/20"><AlertCircle className="w-4 h-4 shrink-0" />{error}</div>}
      {docs.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground"><FileText className="w-12 h-12 mx-auto mb-3 opacity-20" /><p>No documents yet. Upload PDFs, DOCX, TXT, and more.</p></div>
      ) : (
        <div className="space-y-2">
          {docs.map(d => (
            <div key={d.id} className="flex items-center justify-between p-4 rounded-xl bg-card border border-border hover:border-primary/20 transition-all group">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-primary" />
                <div>
                  <p className="text-sm font-medium">{d.filename}</p>
                  <p className="text-xs text-muted-foreground">{d.total_chunks} chunks · {d.status} · {d.file_size_bytes ? `${(d.file_size_bytes/1024).toFixed(0)}KB` : ""}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={cn("text-xs px-2 py-1 rounded-lg", d.status === "ready" ? "bg-success/10 text-success" : d.status === "failed" ? "bg-danger/10 text-danger" : "bg-warning/10 text-warning")}>{d.status}</span>
                <button onClick={() => del(d.id)} className="p-2 rounded-lg hover:bg-danger/10 hover:text-danger text-muted-foreground opacity-0 group-hover:opacity-100 transition-all"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══ CONVERSATIONS TAB ═══ */
function ConversationsTab({ agentId }: { agentId: string }) {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<ApiMessage[]>([]);

  useEffect(() => { api.listConversations(agentId).then(setConvs).catch(console.error); }, [agentId]);

  const loadMsgs = async (convId: string) => {
    setSelected(convId);
    const m = await api.getMessages(agentId, convId);
    setMsgs(m);
  };

  const channelIcon: Record<string, any> = { web: MessageSquare, voice: Phone, whatsapp: MessageSquare, email: Mail };

  return (
    <div className="flex h-[calc(100vh-57px)]">
      <div className="w-80 border-r border-border overflow-y-auto p-4 space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Conversations ({convs.length})</h3>
        {convs.length === 0 ? <p className="text-sm text-muted-foreground text-center py-8">No conversations yet.</p> : convs.map(c => {
          const Icon = channelIcon[c.channel] || MessageSquare;
          return (
            <button key={c.id} onClick={() => loadMsgs(c.id)} className={cn("w-full text-left p-3 rounded-xl transition-all", selected === c.id ? "bg-primary/10 border border-primary/30" : "hover:bg-muted border border-transparent")}>
              <div className="flex items-center gap-2 mb-1">
                <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-xs font-medium capitalize">{c.channel}</span>
                <span className={cn("ml-auto text-[10px] px-1.5 py-0.5 rounded", c.status === "active" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground")}>{c.status}</span>
              </div>
              <p className="text-xs text-muted-foreground">{c.message_count} messages · {new Date(c.started_at).toLocaleDateString()}</p>
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground"><MessageSquare className="w-10 h-10 mb-3 opacity-20" /><p>Select a conversation</p></div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-3">
            {msgs.map(m => (
              <div key={m.id} className={cn("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className={cn("px-4 py-3 text-sm max-w-[80%] rounded-2xl", m.role === "user" ? "bg-primary text-primary-foreground rounded-tr-sm" : "bg-card border border-border rounded-tl-sm")}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  <p className="text-[10px] mt-1 opacity-60">{new Date(m.created_at).toLocaleTimeString()}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══ CALLS TAB ═══ */
function CallsTab({ agentId }: { agentId: string }) {
  const [logs, setLogs] = useState<CallLog[]>([]);
  useEffect(() => { api.listCallLogs(agentId).then(setLogs).catch(console.error); }, [agentId]);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h2 className="text-xl font-bold mb-6">Call Logs</h2>
      {logs.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground"><Phone className="w-12 h-12 mx-auto mb-3 opacity-20" /><p>No call logs yet. Configure voice calling to get started.</p></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wider">
              <th className="pb-3 pr-4">Direction</th><th className="pb-3 pr-4">From</th><th className="pb-3 pr-4">To</th><th className="pb-3 pr-4">Status</th><th className="pb-3 pr-4">Duration</th><th className="pb-3">Date</th>
            </tr></thead>
            <tbody>{logs.map(l => (
              <tr key={l.id} className="border-b border-border/50 hover:bg-muted/30">
                <td className="py-3 pr-4"><span className={cn("text-xs px-2 py-1 rounded-lg", l.direction === "inbound" ? "bg-primary/10 text-primary" : "bg-accent/10 text-accent")}>{l.direction}</span></td>
                <td className="py-3 pr-4 font-mono text-xs">{l.from_number || "—"}</td>
                <td className="py-3 pr-4 font-mono text-xs">{l.to_number || "—"}</td>
                <td className="py-3 pr-4"><span className={cn("text-xs px-2 py-1 rounded-lg", l.status === "completed" ? "bg-success/10 text-success" : l.status === "forwarded" ? "bg-warning/10 text-warning" : "bg-muted text-muted-foreground")}>{l.status}</span></td>
                <td className="py-3 pr-4 text-xs">{l.duration_seconds ? `${l.duration_seconds}s` : "—"}</td>
                <td className="py-3 text-xs text-muted-foreground">{new Date(l.created_at).toLocaleString()}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ═══ SETTINGS TAB ═══ */
function SettingsTab({ agent, onUpdate }: { agent: Agent; onUpdate: (a: Agent) => void }) {
  const [form, setForm] = useState<Partial<AgentCreate>>({
    name: agent.name, description: agent.description || "", system_prompt: agent.system_prompt,
    persona_name: agent.persona_name, voice_id: agent.voice_id,
    call_enabled: agent.call_enabled, whatsapp_enabled: agent.whatsapp_enabled, email_enabled: agent.email_enabled,
    twilio_phone_number: agent.twilio_phone_number || "", forward_phone_number: agent.forward_phone_number || "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateAgent(agent.id, form);
      onUpdate(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { alert("Failed to save"); }
    finally { setSaving(false); }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Agent Settings</h2>
        <button onClick={save} disabled={saving} className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : saved ? "Saved!" : "Save Changes"}
        </button>
      </div>
      <div className="space-y-4">
        <div><label className="block text-sm font-medium mb-2">Agent Name</label><input value={form.name||""} onChange={e=>setForm(p=>({...p,name:e.target.value}))} className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary transition-all" /></div>
        <div><label className="block text-sm font-medium mb-2">Description</label><input value={form.description||""} onChange={e=>setForm(p=>({...p,description:e.target.value}))} className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary transition-all" /></div>
        <div><label className="block text-sm font-medium mb-2">Persona Name</label><input value={form.persona_name||""} onChange={e=>setForm(p=>({...p,persona_name:e.target.value}))} className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary transition-all" /></div>
        <div><label className="block text-sm font-medium mb-2">System Prompt</label><textarea value={form.system_prompt||""} onChange={e=>setForm(p=>({...p,system_prompt:e.target.value}))} rows={8} className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary transition-all resize-y font-mono" /></div>
        <div className="grid grid-cols-2 gap-4">
          <div><label className="block text-sm font-medium mb-2">Twilio Phone</label><input value={form.twilio_phone_number||""} onChange={e=>setForm(p=>({...p,twilio_phone_number:e.target.value}))} placeholder="+1..." className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary transition-all" /></div>
          <div><label className="block text-sm font-medium mb-2">Forward Number</label><input value={form.forward_phone_number||""} onChange={e=>setForm(p=>({...p,forward_phone_number:e.target.value}))} placeholder="+1..." className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary transition-all" /></div>
        </div>
        <div className="flex gap-4">
          {(["call_enabled","whatsapp_enabled","email_enabled"] as const).map(k => (
            <label key={k} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={!!form[k]} onChange={e=>setForm(p=>({...p,[k]:e.target.checked}))} className="w-4 h-4 rounded border-border accent-primary" />
              <span className="text-sm capitalize">{k.replace("_enabled","")}</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
