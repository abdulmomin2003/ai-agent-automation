# 🚀 Local Developer Setup Guide

Welcome to the **AI Sales Agent Platform**! This guide outlines how to get the application (both the Next.js Frontend and the Python FastAPI Backend) running smoothly on your local machine.

## 📌 Prerequisites
1. **Docker Desktop** (Recommended for easiest setup)
2. **OR** Node.js, Python, and Git (for manual setup)

---

## 🐳 0. The Easy Way (Docker)

If you have Docker installed, you can spin up the entire application (Frontend + Backend + Audio Dependencies) with a single command!

1. Ensure your `.env` file is populated in the root directory (see section 1).
2. Open a terminal in the root directory (`Gen_AI/Project/`).
3. Run the following command:
   ```bash
   docker-compose up --build
   ```
4. Wait for the images to build. Once running:
   - **Frontend:** [http://localhost:3000](http://localhost:3000)
   - **Backend API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

*If you prefer to run things manually without Docker, follow the steps below.*

---

## 🔑 1. Environment Variables

We use a single, centralized `.env` file located in the **root** of the repository (not inside the `backend/` or `frontend/` folders). 

1. Create a file named `.env` in the root directory: `Gen_AI/Project/.env`
2. Ensure you have the following keys populated:
```env
# --- Groq (Required for LLM and Whisper STT) ---
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# --- Supabase (Placeholders for now) ---
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres

# --- Other APIs ---
TWILIO_ACCOUNT_SID=...
```

---

## 🐍 2. Backend Setup (FastAPI + AI Pipeline)

The backend handles the FAISS vector database, document parsing, `sentence-transformers` embeddings, Groq LLM generation, Whisper STT, and Edge-TTS.

1. Open a new terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a Python virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - **Windows (Command Prompt):** `venv\Scripts\activate.bat`
   - **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
   - **Mac/Linux:** `source venv/bin/activate`
4. Install all dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the FastAPI development server:
   ```bash
   python main.py
   ```
   *The backend will now be running at `http://localhost:8000`.*
   *You can view the interactive API docs at `http://localhost:8000/docs`.*

---

## ⚛️ 3. Frontend Setup (Next.js + Tailwind)

The frontend is a sleek Next.js SPA with Voice Integration and Document Management.

1. Open a **second, separate terminal** and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install the Node dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   *The frontend will now be running at `http://localhost:3000`.*

---

## 🧪 4. Testing the System
1. Open your browser to [http://localhost:3000](http://localhost:3000).
2. Use the left **Sidebar** to upload a document (PDF, DOCX, TXT, etc.). Wait for the "Vector Chunks" count to increase.
3. In the **Chat Window**, either:
   - Type a question and hit Enter.
   - Click the **Microphone (🎤) icon**, speak your question, and click stop. The system will transcribe your voice using Groq Whisper, query the document, and automatically speak the answer out loud using Edge-TTS!

### 💡 Troubleshooting
- **Missing `FileText` or import errors?** Ensure you ran `npm install` in the frontend directory.
- **Microphone not working?** Check your browser permissions. Voice recording only works on `localhost` or a secure `https` context.
- **Vector DB Errors?** The FAISS database is stored locally inside `backend/data/vector_store`. If it ever gets corrupted, you can safely delete the `data/` folder and restart the server.
