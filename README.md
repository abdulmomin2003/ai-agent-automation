# 🤖 AI Sales Agent Platform

> A self-configuring, multi-tenant AI agent that any business can set up in minutes: upload your documents, define your role, attach a phone number, and go live.

## 📌 Overview

This is a **Generative AI course project** that builds a full-stack AI-powered sales agent platform. The system allows businesses to deploy intelligent conversational agents across multiple channels (voice, SMS, web chat) with zero coding required.

### Key Features

- **Multi-Tenant Architecture** — One platform, unlimited business tenants with data isolation
- **Self-Onboarding** — The AI agent itself guides new businesses through setup
- **Multi-Channel** — Voice (phone via Twilio), SMS, WhatsApp, web chat, email
- **Document-Aware (RAG)** — Upload PDFs/docs to create a knowledge base the agent draws from
- **Tool-Use Enabled** — Books meetings, sends follow-ups, creates CRM records autonomously

## 🏗️ Architecture

The platform consists of 6 layers:

| Layer | Name | Responsibility |
|-------|------|----------------|
| L1 | Tenant Management | Sign-up, API-key wizard, config, multi-tenancy |
| L2 | Communication Gateway | Twilio (voice/SMS), WhatsApp, email |
| L3 | AI Orchestration | LLM, RAG pipeline, conversation memory, tool routing |
| L4 | Tool Execution | Calendar, CRM, SMS/email, web search |
| L5 | Knowledge Base | PDF → chunk → embed → vector store |
| L6 | Dashboard & Analytics | React SPA for configuration and monitoring |

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python) |
| LLM | OpenAI GPT-4o / Anthropic Claude |
| STT/TTS | Deepgram / ElevenLabs |
| Telephony | Twilio Voice + SMS |
| Vector Store | Pinecone / Chroma |
| Database | PostgreSQL (Supabase) |
| Frontend | React + Vite + Tailwind CSS |
| Auth | Supabase Auth |
| Deployment | Railway / Render |

## 📁 Project Structure

```
├── backend/          # FastAPI backend (API, AI orchestration, tools)
├── frontend/         # React + Vite frontend (dashboard, onboarding)
├── docs/             # Project documentation, research papers, proposal
├── .env.example      # Environment variable template
├── .gitignore
└── README.md
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API Key
- Twilio Account (optional, for voice/SMS)
- Pinecone Account (for vector search)
- Supabase Account (for database + auth)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-username>/ai-sales-agent.git
   cd ai-sales-agent
   ```

2. **Backend setup**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   cp .env.example .env
   # Fill in your API keys in .env
   ```

3. **Frontend setup**
   ```bash
   cd frontend
   npm install
   ```

4. **Run the project**
   ```bash
   # Terminal 1 - Backend
   cd backend && uvicorn main:app --reload

   # Terminal 2 - Frontend
   cd frontend && npm run dev
   ```

## 👥 Team

| Name | Role |
|------|------|
| TBD | AI + Backend |
| TBD | Frontend + Integrations |

## 📄 License

This project is developed as part of the Generative AI course (Semester 8, 2025-2026).
