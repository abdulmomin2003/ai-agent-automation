"""
FastAPI application — Multi-Agent AI Sales Platform.

Agent-scoped endpoints for:
- Agent CRUD (create, list, update, delete)
- Knowledge base management (upload, list, delete documents)
- Chat (web chat with conversation persistence)
- Voice queries (STT → RAG → TTS)
- Twilio voice webhooks (inbound calls, call forwarding)
- WhatsApp webhooks
- Health checks
"""

import os
import shutil
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from config import settings
from agent_manager import AgentManager
from db.models import AgentCreate, AgentUpdate, ChatRequest
from twilio_service import (
    build_gather_twiml,
    build_say_and_gather_twiml,
    build_forward_twiml,
    build_hangup_twiml,
    detect_intent,
)
from voice_stream import handle_voice_stream
from web_voice_stream import handle_web_voice_stream
from supabase_health import check_postgres, check_supabase_http

# ── Logging Setup ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global Services ───────────────────────────────────────────

manager: Optional[AgentManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    global manager
    try:
        manager = AgentManager()
        logger.info("Agent Manager initialized — services ready")
    except Exception as e:
        logger.error(f"Failed to initialize Agent Manager: {e}")
    yield
    logger.info("Shutting down")


# ── FastAPI App ────────────────────────────────────────────────

app = FastAPI(
    title="AI Sales Agent Platform — Multi-Agent API",
    description="Create and manage multiple AI agents with voice, chat, WhatsApp, and email.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ──────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    top_k: int = 5
    use_reranking: bool = True


# ── Health Check ───────────────────────────────────────────────

@app.get("/health")
async def health_check(detail: bool = False):
    """Health check endpoint."""
    supabase_http = check_supabase_http()
    postgres = check_postgres()
    payload = {
        "status": "ok",
        "manager_initialized": manager is not None,
        "supabase_connected": supabase_http.ok and postgres.ok,
        "supabase": {
            "url": settings.supabase_url,
            "project_ref": settings.supabase_project_ref,
            "http_ok": supabase_http.ok,
            "postgres_ok": postgres.ok,
        },
    }

    if detail:
        payload["supabase"]["http"] = {
            "ok": supabase_http.ok,
            "detail": supabase_http.detail,
            "data": supabase_http.data,
        }
        payload["supabase"]["postgres"] = {
            "ok": postgres.ok,
            "detail": postgres.detail,
            "data": postgres.data,
        }

    return payload


# ══════════════════════════════════════════════════════════════
# AGENT CRUD
# ══════════════════════════════════════════════════════════════

@app.post("/agents")
async def create_agent(data: AgentCreate):
    """Create a new AI agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    agent = manager.create_agent(data.model_dump(exclude_none=True))
    return {"status": "success", "agent": agent}


@app.get("/agents")
async def list_agents():
    """List all agents."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    agents = manager.list_agents()
    return {"agents": agents}


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    agent = manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent": agent}


@app.put("/agents/{agent_id}")
async def update_agent(agent_id: str, data: AgentUpdate):
    """Update agent configuration."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    agent = manager.update_agent(agent_id, data.model_dump(exclude_none=True))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "agent": agent}


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent and all associated data."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    deleted = manager.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "success", "message": "Agent deleted"}


# ══════════════════════════════════════════════════════════════
# KNOWLEDGE BASE (per agent)
# ══════════════════════════════════════════════════════════════

@app.post("/agents/{agent_id}/upload")
async def upload_document(agent_id: str, file: UploadFile = File(...)):
    """Upload and ingest a document into an agent's knowledge base."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {
        ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls",
        ".csv", ".txt", ".md", ".html", ".htm", ".json",
        ".rtf", ".log", ".xml",
    }:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {ext}")

    # Save to agent-specific directory
    upload_dir = os.path.join(settings.UPLOAD_DIR, agent_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        file_size = os.path.getsize(file_path)
        result = manager.upload_document(
            agent_id=agent_id,
            file_path=file_path,
            filename=file.filename,
            file_type=ext,
            file_size=file_size,
        )

        return {"status": "success", "message": f"Document '{file.filename}' ingested", **result}

    except Exception as e:
        logger.error(f"Error ingesting {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents/{agent_id}/documents")
async def list_documents(agent_id: str):
    """List documents in an agent's knowledge base."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    docs = manager.get_documents(agent_id)
    return {"documents": docs}


@app.delete("/agents/{agent_id}/documents/{doc_id}")
async def delete_document(agent_id: str, doc_id: str):
    """Delete a document from an agent's knowledge base."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    deleted = manager.delete_document(agent_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "success", "message": "Document deleted"}


# ══════════════════════════════════════════════════════════════
# CHAT (per agent)
# ══════════════════════════════════════════════════════════════

@app.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, request: ChatRequest):
    """Send a message to an agent. Creates or resumes a conversation."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        result = manager.chat(
            agent_id=agent_id,
            message=request.message,
            conversation_id=request.conversation_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════
# VOICE QUERY (per agent)
# ══════════════════════════════════════════════════════════════

@app.post("/agents/{agent_id}/voice-query")
async def voice_query(agent_id: str, file: UploadFile = File(...)):
    """Voice query: transcribe audio → RAG → TTS response."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    temp_dir = os.path.join(settings.UPLOAD_DIR, "audio")
    os.makedirs(temp_dir, exist_ok=True)
    temp_input = os.path.join(temp_dir, f"in_{uuid.uuid4().hex[:8]}.webm")

    try:
        with open(temp_input, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = await manager.voice_query(agent_id, temp_input)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Voice query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.remove(temp_input)
        except OSError:
            pass


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve generated audio files."""
    audio_dir = os.path.join(settings.UPLOAD_DIR, "audio")
    file_path = os.path.join(audio_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(file_path, media_type="audio/mpeg")


# ══════════════════════════════════════════════════════════════
# CONVERSATIONS (per agent)
# ══════════════════════════════════════════════════════════════

@app.get("/agents/{agent_id}/conversations")
async def list_conversations(agent_id: str):
    """List all conversations for an agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    convs = manager.get_conversations(agent_id)
    return {"conversations": convs}


@app.get("/agents/{agent_id}/conversations/{conv_id}/messages")
async def get_conversation_messages(agent_id: str, conv_id: str):
    """Get all messages in a conversation."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    messages = manager.get_messages(conv_id)
    return {"messages": messages}


# ══════════════════════════════════════════════════════════════
# CALL LOGS (per agent)
# ══════════════════════════════════════════════════════════════

@app.get("/agents/{agent_id}/call-logs")
async def list_call_logs(agent_id: str):
    """List call logs for an agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    logs = manager.get_call_logs(agent_id)
    return {"call_logs": logs}


# ══════════════════════════════════════════════════════════════
# TWILIO VOICE WEBHOOKS
# ══════════════════════════════════════════════════════════════

@app.post("/twilio/voice/inbound")
async def twilio_voice_inbound(request: Request):
    """
    Twilio inbound voice webhook.

    When someone calls the Twilio number, this endpoint:
    1. Identifies which agent owns the phone number
    2. Greets the caller with the agent's persona
    3. Initiates a WebSocket Media Stream for real-time bidirectional audio
    """
    form = await request.form()
    called_number = form.get("Called", "")
    from_number = form.get("From", "")
    call_sid = form.get("CallSid", "")

    logger.info("Inbound call: %s → %s (SID: %s)", from_number, called_number, call_sid)

    # Find agent by phone number
    if manager:
        agents = manager.list_agents()
        agent = next(
            (a for a in agents if a.get("twilio_phone_number") == called_number),
            None,
        )

        if agent:
            # Log the call
            from db import database as db
            conversation = db.create_conversation(
                str(agent["id"]), channel="voice", caller_phone=from_number
            )
            db.create_call_log(
                agent_id=str(agent["id"]),
                call_sid=call_sid,
                conversation_id=str(conversation["id"]),
                direction="inbound",
                from_number=from_number,
                to_number=called_number,
            )

            # Generate TwiML to connect to WebSocket
            # We get the host from the request headers to build the wss:// URL
            host = request.headers.get("host", "localhost:8000")
            # If running behind ngrok, x-forwarded-proto will be https
            proto = request.headers.get("x-forwarded-proto", "http")
            ws_proto = "wss" if proto == "https" else "ws"
            
            ws_url = f"{ws_proto}://{host}/twilio/voice/stream/{agent['id']}/{conversation['id']}"
            
            greeting = f"Hello! This is {agent.get('persona_name', 'AI Agent')}. How can I help you today?"
            
            twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="{agent.get('voice_id', 'Polly.Joanna')}">{greeting}</Say>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>'''
            return Response(content=twiml, media_type="application/xml")
        
    twiml = build_hangup_twiml("Sorry, the system is not available right now.")
    return Response(content=twiml, media_type="application/xml")

@app.websocket("/twilio/voice/stream/{agent_id}/{conv_id}")
async def websocket_voice_endpoint(websocket: WebSocket, agent_id: str, conv_id: str):
    """
    WebSocket endpoint for Twilio Media Streams.
    Receives audio, processes via VAD/STT/LangGraph, and streams TTS back.
    """
    if manager is None:
        await websocket.close(code=1011)
        return
        
    await handle_voice_stream(websocket, agent_id, conv_id, manager)

@app.websocket("/web/voice/stream/{agent_id}/{conv_id}")
async def web_voice_websocket_endpoint(websocket: WebSocket, agent_id: str, conv_id: str):
    """
    WebSocket endpoint for web browser audio streaming.
    Receives raw PCM audio, performs VAD, and streams TTS back.
    """
    if manager is None:
        await websocket.close(code=1011)
        return
        
    await handle_web_voice_stream(websocket, agent_id, conv_id, manager)


@app.post("/twilio/voice/respond")
async def twilio_voice_respond(request: Request, agent_id: str = None, conv_id: str = None):
    """
    Process speech from caller and respond.

    Flow: Caller speech → Twilio transcription → RAG query → TTS response → loop
    """
    form = await request.form()
    speech_result = form.get("SpeechResult", "")
    call_sid = form.get("CallSid", "")

    logger.info("Voice speech: '%s' (agent=%s)", speech_result[:100], agent_id)

    if not speech_result.strip():
        twiml = build_say_and_gather_twiml(
            text="I didn't catch that. Could you please repeat?",
            action_url=f"/twilio/voice/respond?agent_id={agent_id}&conv_id={conv_id}",
        )
        return Response(content=twiml, media_type="application/xml")

    # Check for special intents (forward, hangup)
    intent = detect_intent(speech_result)

    if intent == "forward" and agent_id and manager:
        agent = manager.get_agent(agent_id)
        forward_number = agent.get("forward_phone_number") if agent else None
        if forward_number:
            from db import database as db
            db.update_call_log(call_sid, status="forwarded", forwarded_to=forward_number)
            twiml = build_forward_twiml(forward_number)
            return Response(content=twiml, media_type="application/xml")

    if intent == "hangup":
        from db import database as db
        db.update_call_log(call_sid, status="completed")
        twiml = build_hangup_twiml()
        return Response(content=twiml, media_type="application/xml")

    # Process through agent RAG pipeline
    if agent_id and manager:
        try:
            result = manager.chat(agent_id, speech_result, conv_id, channel="voice")
            answer = result["answer"]
        except Exception as e:
            logger.error("Voice RAG error: %s", e)
            answer = "I apologize, I'm having trouble processing your request right now."
    else:
        answer = "I'm sorry, I'm not configured to help with that right now."

    # Respond and loop
    twiml = build_say_and_gather_twiml(
        text=answer,
        action_url=f"/twilio/voice/respond?agent_id={agent_id}&conv_id={conv_id}",
    )
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/voice/status")
async def twilio_voice_status(request: Request):
    """Twilio call status callback."""
    form = await request.form()
    call_sid = form.get("CallSid", "")
    call_status = form.get("CallStatus", "")
    duration = form.get("CallDuration")

    logger.info("Call status: %s → %s (duration=%s)", call_sid, call_status, duration)

    if call_sid:
        from db import database as db
        db.update_call_log(
            call_sid,
            status=call_status,
            duration_seconds=int(duration) if duration else None,
        )

    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════
# WHATSAPP WEBHOOK
# ══════════════════════════════════════════════════════════════

@app.post("/twilio/whatsapp/inbound")
async def twilio_whatsapp_inbound(request: Request):
    """
    Twilio WhatsApp inbound webhook.

    Processes incoming WhatsApp messages through the agent's RAG pipeline.
    """
    form = await request.form()
    from_number = form.get("From", "").replace("whatsapp:", "")
    to_number = form.get("To", "").replace("whatsapp:", "")
    body = form.get("Body", "")

    logger.info("WhatsApp from %s: %s", from_number, body[:100])

    if not body.strip() or not manager:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )

    # Find agent by phone number
    agents = manager.list_agents()
    agent = next(
        (a for a in agents
         if a.get("twilio_phone_number") == to_number and a.get("whatsapp_enabled")),
        None,
    )

    if agent:
        try:
            result = manager.chat(
                str(agent["id"]), body, channel="whatsapp"
            )
            reply = result["answer"]
        except Exception as e:
            logger.error("WhatsApp RAG error: %s", e)
            reply = "Sorry, I'm having trouble right now. Please try again."
    else:
        reply = "This number is not configured for WhatsApp messaging."

    # Build TwiML response
    from xml.etree.ElementTree import Element, SubElement, tostring
    resp = Element("Response")
    msg = SubElement(resp, "Message")
    msg.text = reply[:4096]

    twiml = '<?xml version="1.0" encoding="UTF-8"?>' + tostring(resp, encoding="unicode")
    return Response(content=twiml, media_type="application/xml")


# ══════════════════════════════════════════════════════════════
# DYNAMIC TOOLS (per agent)
# ══════════════════════════════════════════════════════════════

class AgentToolCreate(BaseModel):
    name: str
    description: str
    method: str = "POST"
    webhook_url: str
    parameters_schema: dict = {}

@app.get("/agents/{agent_id}/tools")
async def list_agent_tools(agent_id: str):
    """List custom tools for an agent."""
    from db import database as db
    tools = db.get_agent_tools(agent_id)
    return {"tools": tools}

@app.post("/agents/{agent_id}/tools")
async def create_agent_tool(agent_id: str, data: AgentToolCreate):
    """Create a new custom tool for an agent."""
    from db import database as db
    tool = db.create_agent_tool(agent_id, data.model_dump())
    return {"status": "success", "tool": tool}

@app.delete("/agents/{agent_id}/tools/{tool_id}")
async def delete_agent_tool(agent_id: str, tool_id: str):
    """Delete a custom tool."""
    from db import database as db
    success = db.delete_agent_tool(tool_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════
# AVAILABILITY CONFIG (per agent)
# ══════════════════════════════════════════════════════════════

class AvailabilityEntry(BaseModel):
    day_of_week: int           # 0=Monday … 6=Sunday
    start_time: str            # HH:MM
    end_time: str              # HH:MM
    slot_duration_minutes: int = 60
    is_active: bool = True

@app.get("/agents/{agent_id}/availability")
async def get_availability(agent_id: str):
    """Get weekly availability schedule for an agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    config = manager.get_availability(agent_id)
    return {"availability": config}

@app.put("/agents/{agent_id}/availability")
async def set_availability(agent_id: str, schedule: list[AvailabilityEntry]):
    """Set weekly availability schedule for an agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    result = manager.set_availability(agent_id, [e.model_dump() for e in schedule])
    return {"status": "success", "availability": result}


# ══════════════════════════════════════════════════════════════
# BOOKINGS (per agent)
# ══════════════════════════════════════════════════════════════

class BookingCreate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    booking_date: str
    booking_time: str
    duration_minutes: int = 60
    notes: Optional[str] = None

@app.get("/agents/{agent_id}/bookings/slots")
async def get_booking_slots(agent_id: str, date: str):
    """Get available booking slots for a specific date."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    slots = manager.get_available_slots(agent_id, date)
    return {"date": date, "available_slots": slots}

@app.get("/agents/{agent_id}/bookings")
async def list_bookings(agent_id: str, date: Optional[str] = None):
    """List all bookings for an agent, optionally filtered by date."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    bookings = manager.get_bookings(agent_id, date)
    return {"bookings": bookings}

@app.post("/agents/{agent_id}/bookings")
async def create_booking(agent_id: str, data: BookingCreate):
    """Create a new booking (also sends confirmation email if customer_email provided)."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from db import database as db
    try:
        booking = db.create_booking(agent_id, data.model_dump())
        # Send confirmation email if email provided
        if data.customer_email:
            agent = manager.get_agent(agent_id)
            if agent:
                from email_service import EmailService
                email_svc = EmailService(from_name=agent.get("persona_name", "AI Agent"))
                sent = email_svc.send_booking_confirmation_sync(
                    to_email=data.customer_email,
                    agent_name=agent.get("persona_name", agent.get("name", "AI Agent")),
                    customer_name=data.customer_name or "Customer",
                    booking_date=data.booking_date,
                    booking_time=data.booking_time,
                    notes=data.notes or "",
                )
                if sent:
                    db.mark_booking_email_sent(booking["id"])
        return {"status": "success", "booking": booking}
    except Exception as e:
        logger.error("Booking error: %s", e)
        raise HTTPException(status_code=400, detail="Failed to create booking. Slot might be taken.")

@app.patch("/agents/{agent_id}/bookings/{booking_id}/cancel")
async def cancel_booking(agent_id: str, booking_id: str):
    """Cancel a booking and send cancellation email."""
    from db import database as db
    booking = db.get_booking_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    db.update_booking_status(booking_id, "cancelled")
    # Send cancellation email
    if booking.get("customer_email") and manager:
        agent = manager.get_agent(agent_id)
        if agent:
            from email_service import EmailService
            email_svc = EmailService(from_name=agent.get("persona_name", "AI Agent"))
            email_svc.send_cancellation_sync(
                to_email=booking["customer_email"],
                agent_name=agent.get("persona_name", agent.get("name", "AI Agent")),
                customer_name=booking.get("customer_name", "Customer"),
                booking_date=booking.get("booking_date", ""),
                booking_time=booking.get("booking_time", ""),
            )
    return {"status": "success", "message": "Booking cancelled"}


# ══════════════════════════════════════════════════════════════
# CONVERSATION SUMMARY
# ══════════════════════════════════════════════════════════════

@app.post("/agents/{agent_id}/conversations/{conv_id}/end")
async def end_conversation(agent_id: str, conv_id: str):
    """
    End a conversation: generate LLM summary, store it, and optionally
    send a follow-up email if the conversation has a caller_email.
    """
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        summary = manager.generate_and_store_summary(agent_id, conv_id)
        # Auto-send follow-up email if conversation has a caller email
        from db import database as db
        conv = db.get_conversation(conv_id)
        if conv and conv.get("caller_email"):
            agent = manager.get_agent(agent_id)
            if agent and agent.get("send_summary_emails", True):
                await manager.send_conversation_summary_email(
                    agent_id, conv_id, conv["caller_email"], summary
                )
        return {"status": "success", "summary": summary}
    except Exception as e:
        logger.error("Error ending conversation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agents/{agent_id}/conversations/{conv_id}/summary")
async def generate_summary(agent_id: str, conv_id: str):
    """Manually trigger summary generation for a conversation."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        summary = manager.generate_and_store_summary(agent_id, conv_id)
        return {"status": "success", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ══════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS (backward compatibility)
# ══════════════════════════════════════════════════════════════

@app.post("/upload")
async def upload_document_legacy(file: UploadFile = File(...)):
    """Legacy upload — redirects to first available agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    agents = manager.list_agents()
    if not agents:
        raise HTTPException(status_code=400, detail="No agents exist. Create an agent first.")
    return await upload_document(str(agents[0]["id"]), file)


@app.post("/query")
async def query_legacy(request: QueryRequest):
    """Legacy query — uses first available agent."""
    if manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    agents = manager.list_agents()
    if not agents:
        raise HTTPException(status_code=400, detail="No agents exist. Create an agent first.")

    chat_req = ChatRequest(
        message=request.question,
        conversation_id=request.conversation_id,
    )
    return await chat_with_agent(str(agents[0]["id"]), chat_req)


# ── Run ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
