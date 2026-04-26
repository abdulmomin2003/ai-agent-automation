"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, Sparkles, ChevronDown, ChevronUp, FileText, Mic, Square } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, QueryResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  context_chunks?: QueryResponse["context_chunks"];
  audio_url?: string;
};

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "Hello! I'm your AI Sales Agent. You can type or use the microphone to talk to me.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleVoiceResponse = (audioUrl: string) => {
    // Automatically play the returned audio
    const audio = new Audio(process.env.NEXT_PUBLIC_API_URL ? `${process.env.NEXT_PUBLIC_API_URL}${audioUrl}` : `http://localhost:8000${audioUrl}`);
    audio.play().catch(e => console.error("Auto-play failed:", e));
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        setIsLoading(true);

        try {
          const res = await api.voiceQuery(audioBlob);
          
          // Add User Message (transcribed)
          setMessages((prev) => [
            ...prev,
            { id: Date.now().toString(), role: "user", content: res.question }
          ]);

          // Add AI Message
          setMessages((prev) => [
            ...prev,
            {
              id: (Date.now() + 1).toString(),
              role: "assistant",
              content: res.answer,
              sources: res.sources,
              context_chunks: res.context_chunks,
              audio_url: res.audio_url
            }
          ]);

          if (res.audio_url) {
            handleVoiceResponse(res.audio_url);
          }
        } catch (err) {
          console.error("Voice query error", err);
          setMessages((prev) => [
            ...prev,
            { id: Date.now().toString(), role: "assistant", content: "Sorry, I had trouble processing your voice." }
          ]);
        } finally {
          setIsLoading(false);
          // Stop all tracks
          stream.getTracks().forEach(track => track.stop());
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Microphone access denied", err);
      alert("Please allow microphone access to use voice chat.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const history = messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await api.query(userMsg.content, history);

      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: res.answer,
        sources: res.sources,
        context_chunks: res.context_chunks,
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      console.error("Chat error", err);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "Sorry, I encountered an error communicating with the server.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-background relative">
      {/* Header */}
      <header className="h-16 border-b border-border flex items-center px-6 shrink-0 bg-card/50 backdrop-blur-md z-10 sticky top-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="font-semibold text-sm">AI Agent Chat</h2>
            <p className="text-xs text-muted-foreground">Voice Enabled (Whisper + Edge TTS)</p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 pb-32">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
          {isLoading && (
            <div className="flex gap-4 p-4 rounded-2xl bg-card border border-border w-fit max-w-[80%] animate-pulse">
              <div className="w-8 h-8 shrink-0 rounded-full bg-primary/20 flex items-center justify-center">
                <Loader2 className="w-4 h-4 text-primary animate-spin" />
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-2 h-2 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-2 h-2 rounded-full bg-primary/40 animate-bounce"></div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="absolute bottom-0 inset-x-0 p-4 bg-gradient-to-t from-background via-background to-transparent pt-10">
        <div className="max-w-3xl mx-auto">
          <form
            onSubmit={handleSubmit}
            className={cn(
              "relative flex items-end gap-2 bg-card border rounded-2xl p-2 shadow-sm transition-all",
              isRecording ? "border-red-500/50 ring-2 ring-red-500/20" : "border-border focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary"
            )}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder={isRecording ? "Listening..." : "Ask a question..."}
              disabled={isRecording}
              className="flex-1 max-h-40 min-h-[44px] bg-transparent resize-none outline-none py-3 px-3 text-sm disabled:opacity-50"
              rows={1}
            />
            
            <div className="flex items-center gap-1 mb-0.5 mr-0.5">
              {isRecording ? (
                <button
                  type="button"
                  onClick={stopRecording}
                  className="w-11 h-11 shrink-0 bg-red-500 hover:bg-red-600 text-white rounded-xl flex items-center justify-center transition-all animate-pulse"
                >
                  <Square className="w-4 h-4 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={startRecording}
                  disabled={isLoading}
                  className="w-11 h-11 shrink-0 bg-muted hover:bg-muted/80 text-foreground rounded-xl flex items-center justify-center transition-all disabled:opacity-50"
                  title="Use Microphone"
                >
                  <Mic className="w-5 h-5" />
                </button>
              )}
              <button
                type="submit"
                disabled={!input.trim() || isLoading || isRecording}
                className="w-11 h-11 shrink-0 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl flex items-center justify-center transition-all disabled:opacity-50 disabled:hover:bg-primary"
              >
                <Send className="w-5 h-5 ml-0.5" />
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  const [showSources, setShowSources] = useState(false);

  return (
    <div className={cn("flex gap-4 group", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="w-8 h-8 shrink-0 rounded-full bg-primary/20 flex items-center justify-center mt-1">
          <Bot className="w-4 h-4 text-primary" />
        </div>
      )}

      <div
        className={cn(
          "relative flex flex-col px-5 py-4 text-sm max-w-[85%] sm:max-w-[75%]",
          isUser
            ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
            : "bg-card border border-border text-card-foreground rounded-2xl rounded-tl-sm shadow-sm"
        )}
      >
        <div className={cn("prose prose-sm max-w-none break-words", isUser ? "prose-invert" : "dark:prose-invert")}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
        </div>

        {/* Audio Player for TTS */}
        {msg.audio_url && (
          <div className="mt-3">
            <audio controls className="h-8 w-full max-w-[200px]" src={process.env.NEXT_PUBLIC_API_URL ? `${process.env.NEXT_PUBLIC_API_URL}${msg.audio_url}` : `http://localhost:8000${msg.audio_url}`} />
          </div>
        )}

        {/* Source Citations */}
        {msg.sources && msg.sources.length > 0 && (
          <div className="mt-4 pt-3 border-t border-border/50">
            <button
              onClick={() => setShowSources(!showSources)}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>{msg.sources.length} Sources Used</span>
              {showSources ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
            </button>

            {showSources && (
              <div className="mt-3 space-y-2">
                {msg.sources.map((src, i) => (
                  <div key={i} className="px-2.5 py-1.5 bg-muted rounded-md text-xs font-medium flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary/60"></div>
                    {src}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 shrink-0 rounded-full bg-muted flex items-center justify-center mt-1">
          <User className="w-4 h-4 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
