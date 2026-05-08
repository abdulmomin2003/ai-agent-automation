"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, ArrowRight, Bot, FileText, Settings, Phone,
  MessageSquare, Mail, Mic, Loader2, Check, Sparkles,
} from "lucide-react";
import { api, AgentCreate } from "@/lib/api";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: 1, label: "Basic Info", icon: Bot },
  { id: 2, label: "Knowledge & Prompt", icon: FileText },
  { id: 3, label: "Channels & Voice", icon: Phone },
  { id: 4, label: "API Keys", icon: Settings },
];

const VOICE_OPTIONS = [
  { id: "en-US-AriaNeural", label: "Aria (Female, US)", type: "edge-tts" },
  { id: "en-US-GuyNeural", label: "Guy (Male, US)", type: "edge-tts" },
  { id: "en-US-JennyNeural", label: "Jenny (Female, US)", type: "edge-tts" },
  { id: "en-GB-SoniaNeural", label: "Sonia (Female, UK)", type: "edge-tts" },
  { id: "en-GB-RyanNeural", label: "Ryan (Male, UK)", type: "edge-tts" },
  { id: "en-AU-NatashaNeural", label: "Natasha (Female, AU)", type: "edge-tts" },
];

const INDUSTRY_PRESETS = [
  {
    name: "Law Firm",
    description: "Legal consultation and appointment booking",
    prompt: "You are a professional legal assistant for a law firm. You help potential clients understand legal services, schedule consultations, and answer basic legal questions based on the firm's practice areas. Always recommend scheduling a consultation for specific legal advice. Be professional, empathetic, and clear.",
    persona: "Legal Assistant",
  },
  {
    name: "Plumber / Trades",
    description: "Service booking and emergency dispatch",
    prompt: "You are a helpful booking assistant for a plumbing/trades company. Help customers describe their issue, assess urgency, provide rough estimates if possible, and book appointments. For emergencies, escalate by forwarding the call. Be friendly, professional, and reassuring.",
    persona: "Service Coordinator",
  },
  {
    name: "Medical Clinic",
    description: "Patient intake and appointment scheduling",
    prompt: "You are a medical clinic receptionist AI. Help patients schedule appointments, answer questions about services and hours, and collect basic intake information. Never provide medical diagnoses. For urgent symptoms, advise calling emergency services. Be warm, professional, and HIPAA-aware.",
    persona: "Clinic Receptionist",
  },
  {
    name: "Restaurant",
    description: "Reservation booking and menu inquiries",
    prompt: "You are a friendly restaurant assistant. Help customers make reservations, answer questions about the menu, share information about specials and events, and handle dietary restriction inquiries. Be warm, enthusiastic about the food, and helpful.",
    persona: "Restaurant Host",
  },
  {
    name: "Real Estate",
    description: "Property inquiries and showing scheduling",
    prompt: "You are a real estate assistant. Help potential buyers and renters learn about available properties, schedule viewings, and answer questions about neighborhoods, pricing, and features. Collect contact information for follow-up. Be knowledgeable and professional.",
    persona: "Property Advisor",
  },
  {
    name: "Custom",
    description: "Start from scratch with your own prompt",
    prompt: "You are a helpful AI assistant. Answer questions based on the provided knowledge base.",
    persona: "AI Agent",
  },
];

export default function NewAgentPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [creating, setCreating] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<number | null>(null);

  const [form, setForm] = useState<AgentCreate>({
    name: "",
    description: "",
    system_prompt: "You are a helpful AI assistant. Answer questions based on the provided knowledge base.",
    persona_name: "AI Agent",
    voice_id: "en-US-AriaNeural",
    call_enabled: false,
    whatsapp_enabled: false,
    email_enabled: false,
    twilio_phone_number: "",
    forward_phone_number: "",
    groq_api_key: "",
    elevenlabs_api_key: "",
  });

  const updateForm = (field: keyof AgentCreate, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const selectPreset = (index: number) => {
    const preset = INDUSTRY_PRESETS[index];
    setSelectedPreset(index);
    setForm((prev) => ({
      ...prev,
      description: preset.description,
      system_prompt: preset.prompt,
      persona_name: preset.persona,
    }));
  };

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    setCreating(true);
    try {
      // Clean up empty strings to avoid sending them
      const payload: AgentCreate = { ...form };
      if (!payload.groq_api_key) delete payload.groq_api_key;
      if (!payload.elevenlabs_api_key) delete payload.elevenlabs_api_key;
      if (!payload.twilio_phone_number) delete payload.twilio_phone_number;
      if (!payload.forward_phone_number) delete payload.forward_phone_number;

      const agent = await api.createAgent(payload);
      router.push(`/agents/${agent.id}`);
    } catch (err) {
      console.error("Failed to create agent", err);
      alert("Failed to create agent. Check backend connection.");
    } finally {
      setCreating(false);
    }
  };

  const canProceed = () => {
    if (step === 1) return form.name.trim().length > 0;
    return true;
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </button>
          <div className="flex items-center gap-2">
            {STEPS.map((s, i) => (
              <div key={s.id} className="flex items-center gap-2">
                <button
                  onClick={() => step > s.id && setStep(s.id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                    step === s.id
                      ? "bg-primary text-primary-foreground"
                      : step > s.id
                      ? "bg-primary/10 text-primary cursor-pointer"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  {step > s.id ? <Check className="w-3 h-3" /> : <s.icon className="w-3 h-3" />}
                  <span className="hidden sm:inline">{s.label}</span>
                </button>
                {i < STEPS.length - 1 && (
                  <div className={cn("w-8 h-px", step > s.id ? "bg-primary/30" : "bg-border")} />
                )}
              </div>
            ))}
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* Step 1: Basic Info */}
        {step === 1 && (
          <div className="space-y-8">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Create a New Agent</h2>
              <p className="text-muted-foreground">Choose an industry template or start from scratch</p>
            </div>

            {/* Industry Presets */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
              {INDUSTRY_PRESETS.map((preset, i) => (
                <button
                  key={preset.name}
                  onClick={() => selectPreset(i)}
                  className={cn(
                    "p-4 rounded-xl border text-left transition-all",
                    selectedPreset === i
                      ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                      : "border-border hover:border-primary/30 hover:bg-card"
                  )}
                >
                  <p className="font-medium text-sm mb-1">{preset.name}</p>
                  <p className="text-xs text-muted-foreground line-clamp-2">{preset.description}</p>
                </button>
              ))}
            </div>

            {/* Name & Description */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Agent Name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => updateForm("name", e.target.value)}
                  placeholder="e.g., Smith & Associates Legal, Joe's Plumbing..."
                  className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Description</label>
                <input
                  type="text"
                  value={form.description || ""}
                  onChange={(e) => updateForm("description", e.target.value)}
                  placeholder="Brief description of what this agent does..."
                  className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Persona Name</label>
                <input
                  type="text"
                  value={form.persona_name || ""}
                  onChange={(e) => updateForm("persona_name", e.target.value)}
                  placeholder="e.g., Sarah, Assistant, Receptionist..."
                  className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Knowledge & Prompt */}
        {step === 2 && (
          <div className="space-y-6">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Knowledge & Behavior</h2>
              <p className="text-muted-foreground">Define how your agent thinks and responds</p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                System Prompt
                <span className="text-muted-foreground font-normal ml-2">
                  (Instructions for the AI — tone, rules, capabilities)
                </span>
              </label>
              <textarea
                value={form.system_prompt || ""}
                onChange={(e) => updateForm("system_prompt", e.target.value)}
                rows={10}
                className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all resize-y font-mono"
                placeholder="You are a helpful assistant..."
              />
              <p className="text-xs text-muted-foreground mt-2">
                Tip: Be specific about your business, services, tone, and what the agent should/shouldn&apos;t do.
                You&apos;ll upload knowledge documents after creating the agent.
              </p>
            </div>
          </div>
        )}

        {/* Step 3: Channels & Voice */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Channels & Voice</h2>
              <p className="text-muted-foreground">Configure communication channels and voice settings</p>
            </div>

            {/* Channel Toggles */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Channels</h3>
              
              {[
                { key: "call_enabled" as const, icon: Phone, label: "Voice Calls", desc: "Receive and make phone calls via Twilio" },
                { key: "whatsapp_enabled" as const, icon: MessageSquare, label: "WhatsApp", desc: "Handle WhatsApp messages" },
                { key: "email_enabled" as const, icon: Mail, label: "Email", desc: "Send follow-up emails via SendGrid" },
              ].map((ch) => (
                <div
                  key={ch.key}
                  className={cn(
                    "flex items-center justify-between p-4 rounded-xl border transition-all",
                    form[ch.key] ? "border-primary/30 bg-primary/5" : "border-border bg-card"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center",
                      form[ch.key] ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
                    )}>
                      <ch.icon className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{ch.label}</p>
                      <p className="text-xs text-muted-foreground">{ch.desc}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => updateForm(ch.key, !form[ch.key])}
                    className={cn(
                      "w-12 h-7 rounded-full transition-all relative",
                      form[ch.key] ? "bg-primary" : "bg-muted"
                    )}
                  >
                    <div className={cn(
                      "w-5 h-5 rounded-full bg-white absolute top-1 transition-all",
                      form[ch.key] ? "left-6" : "left-1"
                    )} />
                  </button>
                </div>
              ))}
            </div>

            {/* Phone Numbers (if voice enabled) */}
            {form.call_enabled && (
              <div className="space-y-4 pt-4">
                <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Phone Settings</h3>
                <div>
                  <label className="block text-sm font-medium mb-2">Twilio Phone Number</label>
                  <input
                    type="text"
                    value={form.twilio_phone_number || ""}
                    onChange={(e) => updateForm("twilio_phone_number", e.target.value)}
                    placeholder="+19787753952"
                    className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Call Forwarding Number (optional)</label>
                  <input
                    type="text"
                    value={form.forward_phone_number || ""}
                    onChange={(e) => updateForm("forward_phone_number", e.target.value)}
                    placeholder="+1234567890"
                    className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    When a caller asks to speak to a human, the call will be forwarded to this number.
                  </p>
                </div>
              </div>
            )}

            {/* Voice Selection */}
            <div className="space-y-3 pt-4">
              <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Voice</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {VOICE_OPTIONS.map((voice) => (
                  <button
                    key={voice.id}
                    onClick={() => updateForm("voice_id", voice.id)}
                    className={cn(
                      "flex items-center gap-2 p-3 rounded-xl border text-left text-sm transition-all",
                      form.voice_id === voice.id
                        ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                        : "border-border hover:border-primary/30"
                    )}
                  >
                    <Mic className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div>
                      <p className="font-medium text-xs">{voice.label}</p>
                      <p className="text-[10px] text-muted-foreground">{voice.type}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Step 4: API Keys */}
        {step === 4 && (
          <div className="space-y-6">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">API Keys (Optional)</h2>
              <p className="text-muted-foreground">
                Override global API keys for this specific agent. Leave blank to use defaults.
              </p>
            </div>

            <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 text-sm text-primary">
              <Sparkles className="w-4 h-4 inline mr-2" />
              All API keys are optional. The platform uses global keys from .env by default.
              Per-agent keys let different agents use different accounts.
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Groq API Key</label>
                <input
                  type="password"
                  value={form.groq_api_key || ""}
                  onChange={(e) => updateForm("groq_api_key", e.target.value)}
                  placeholder="gsk_... (leave blank for global key)"
                  className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all font-mono"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">ElevenLabs API Key</label>
                <input
                  type="password"
                  value={form.elevenlabs_api_key || ""}
                  onChange={(e) => updateForm("elevenlabs_api_key", e.target.value)}
                  placeholder="sk_... (leave blank for Edge-TTS free voices)"
                  className="w-full px-4 py-3 rounded-xl bg-card border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all font-mono"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Enables premium ElevenLabs voices. Without it, free Edge-TTS voices are used.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Navigation Buttons */}
        <div className="flex justify-between mt-10 pt-6 border-t border-border">
          <button
            onClick={() => step > 1 ? setStep(step - 1) : router.push("/")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl border border-border text-sm font-medium hover:bg-muted transition-all"
          >
            <ArrowLeft className="w-4 h-4" />
            {step > 1 ? "Back" : "Cancel"}
          </button>
          {step < 4 ? (
            <button
              onClick={() => setStep(step + 1)}
              disabled={!canProceed()}
              className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-50"
            >
              Next
              <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleCreate}
              disabled={creating || !form.name.trim()}
              className="flex items-center gap-2 bg-gradient-to-r from-primary to-accent hover:opacity-90 text-white px-6 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-50 shadow-md"
            >
              {creating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              {creating ? "Creating..." : "Create Agent"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
