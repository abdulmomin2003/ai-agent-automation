import asyncio
import logging
import audioop
import wave
import os
import uuid
from fastapi import WebSocket, WebSocketDisconnect

from config import settings
from agent_manager import AgentManager

logger = logging.getLogger(__name__)

FILLER_AUDIO_BYTES = None

async def get_filler_audio(tts, voice_id):
    global FILLER_AUDIO_BYTES
    if FILLER_AUDIO_BYTES is None:
        logger.info("Generating filler audio...")
        path = await tts.generate_speech("Let me quickly check my notes on that for you...", voice_id=voice_id)
        with open(path, "rb") as f:
            FILLER_AUDIO_BYTES = f.read()
        os.remove(path)
    return FILLER_AUDIO_BYTES

# Constants for web silence detection
SILENCE_THRESHOLD = 800  # Adjust based on mic sensitivity
SILENCE_DURATION = 0.7   # Seconds of silence (lowered for faster response)
SAMPLE_RATE = 16000      # Standard WebAudio sample rate for STT

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)


stream_manager = ConnectionManager()

async def handle_web_voice_stream(websocket: WebSocket, agent_id: str, conv_id: str, agent_manager: AgentManager):
    """
    Handles bidirectional web voice stream.
    Receives raw 16kHz Int16 PCM binary data from the browser.
    """
    await stream_manager.connect(websocket)
    
    audio_buffer = bytearray()
    silence_frames = 0
    is_speaking = False
    state = {"processing": False}
    conversation_history = []
    
    # Approx frames based on the chunk size the browser sends
    # Assuming the browser sends a chunk every ~100ms
    frames_per_second = 10
    silence_frames_threshold = int(SILENCE_DURATION * frames_per_second)

    try:
        while True:
            # Receive binary chunk from browser
            data = await websocket.receive_bytes()
            
            if state["processing"]:
                continue
                
            audio_buffer.extend(data)
            
            # Calculate RMS to detect voice activity
            try:
                rms = audioop.rms(data, 2)  # 2 bytes = 16-bit PCM
            except Exception:
                rms = 0
                
            if rms > SILENCE_THRESHOLD:
                if not is_speaking:
                    # User just started speaking! Tell frontend to interrupt any playing audio immediately
                    await websocket.send_json({"type": "interrupt"})
                is_speaking = True
                silence_frames = 0
            elif is_speaking:
                silence_frames += 1
                
            if is_speaking and silence_frames > silence_frames_threshold:
                logger.info("Web user silence detected. Processing audio...")
                state["processing"] = True
                is_speaking = False
                silence_frames = 0
                
                audio_bytes = bytes(audio_buffer)
                audio_buffer.clear()
                
                # We do not await here so the socket can keep reading
                asyncio.create_task(
                    process_web_audio(websocket, audio_bytes, agent_id, conv_id, agent_manager, conversation_history, callback=lambda: state.update({"processing": False}))
                )
                
    except WebSocketDisconnect:
        logger.info("Web client disconnected")
    except Exception as e:
        logger.error(f"Web voice stream error: {e}")
    finally:
        stream_manager.disconnect(websocket)

async def safe_send_json(websocket: WebSocket, data: dict):
    try:
        await websocket.send_json(data)
    except Exception:
        pass

async def safe_send_bytes(websocket: WebSocket, data: bytes):
    try:
        await websocket.send_bytes(data)
    except Exception:
        pass

async def process_web_audio(
    websocket: WebSocket, 
    audio_bytes: bytes, 
    agent_id: str, 
    conv_id: str,
    agent_manager: AgentManager,
    conversation_history: list,
    callback
):
    temp_wav = f"temp_web_{uuid.uuid4().hex}.wav"
    try:
        # Web client sends raw 16kHz Int16 PCM. Wrap in WAV header.
        with wave.open(temp_wav, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_bytes)
            
        from audio_service import AudioService
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            return
            
        audio_svc = AudioService(api_key=agent.get("groq_api_key") or settings.GROQ_API_KEY)
        text = audio_svc.transcribe_audio(temp_wav)
        
        if not text.strip() or len(text) < 2:
            return
            
        # Send transcription back for UI updates
        await safe_send_json(websocket, {"type": "transcription", "text": text, "role": "user"})
            
        tts = agent_manager._get_tts(agent)
        voice_id = agent.get("voice_id", "en-US-AriaNeural")
        loop = asyncio.get_running_loop()

        def on_tool_call(tool_name):
            if tool_name == "search_knowledge_base":
                async def send_filler():
                    try:
                        filler = await get_filler_audio(tts, voice_id)
                        await safe_send_json(websocket, {"type": "audio_start"})
                        await safe_send_bytes(websocket, filler)
                        await safe_send_json(websocket, {"type": "audio_end"})
                    except Exception as e:
                        logger.error(f"Failed to send filler audio: {e}")
                
                asyncio.run_coroutine_threadsafe(send_filler(), loop)

        # Run pipeline query in thread directly (bypassing DB)
        pipeline = agent_manager._get_pipeline(agent_id, agent)
        result = await asyncio.to_thread(
            pipeline.query,
            question=text, 
            conversation_history=conversation_history,
            top_k=5,
            use_reranking=True,
            on_tool_call=on_tool_call
        )
        answer = result["answer"]
        sources = result.get("sources", [])
        
        # Update in-memory history
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": answer})
        if len(conversation_history) > 12:  # Keep last 6 turns
            conversation_history[:] = conversation_history[-12:]
            
        # Dispatch background DB log task
        asyncio.create_task(
            asyncio.to_thread(
                agent_manager.log_chat_background,
                agent_id, text, answer, sources, conv_id, "voice"
            )
        )
        
        await safe_send_json(websocket, {"type": "transcription", "text": answer, "role": "assistant"})
        
        # TTS for the actual answer
        audio_file_path = await tts.generate_speech(answer, voice_id=voice_id)
        
        # Stream the MP3 back directly. The browser's AudioContext can decode MP3 chunks or play as array buffer.
        # But to be safe, we can read the file and send as base64 or binary.
        with open(audio_file_path, "rb") as f:
            mp3_data = f.read()
            
        # Send a json message to indicate audio is coming
        await safe_send_json(websocket, {"type": "audio_start"})
        
        # Send the binary audio file payload
        await safe_send_bytes(websocket, mp3_data)
        
        await safe_send_json(websocket, {"type": "audio_end"})
        
        os.remove(audio_file_path)
        
    except Exception as e:
        logger.error(f"Error processing web audio: {e}")
        await safe_send_json(websocket, {"type": "error", "message": "Failed to process audio"})
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        callback()
        await safe_send_json(websocket, {"type": "ready"})
