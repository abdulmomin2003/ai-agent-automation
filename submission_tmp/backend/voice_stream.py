import base64
import json
import logging
import asyncio
import audioop
import wave
import os
import uuid
from fastapi import WebSocket, WebSocketDisconnect

from config import settings
from agent_manager import AgentManager

logger = logging.getLogger(__name__)

# Constants for silence detection
SILENCE_THRESHOLD = 500  # RMS value below which is considered silence
SILENCE_DURATION = 1.5   # Seconds of silence to trigger end of speech
SAMPLE_RATE = 8000       # Twilio sample rate

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

async def handle_voice_stream(websocket: WebSocket, agent_id: str, conv_id: str, agent_manager: AgentManager):
    """
    Handles bidirectional Twilio Media Stream via WebSocket.
    """
    await stream_manager.connect(websocket)
    stream_sid = None
    
    # State for audio accumulation
    audio_buffer = bytearray()
    silence_frames = 0
    is_speaking = False
    processing = False
    
    # Twilio sends 20ms chunks (160 bytes of mu-law at 8000Hz)
    frames_per_second = 50
    silence_frames_threshold = int(SILENCE_DURATION * frames_per_second)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg["event"] == "start":
                stream_sid = msg["start"]["streamSid"]
                logger.info(f"Started stream: {stream_sid}")
                
            elif msg["event"] == "media":
                if processing:
                    continue  # Ignore audio while processing LLM response
                
                payload = msg["media"]["payload"]
                chunk = base64.b64decode(payload)
                audio_buffer.extend(chunk)
                
                # Decode mu-law to linear PCM (16-bit) for RMS calculation
                pcm_data = audioop.ulaw2lin(chunk, 2)
                rms = audioop.rms(pcm_data, 2)
                
                if rms > SILENCE_THRESHOLD:
                    is_speaking = True
                    silence_frames = 0
                elif is_speaking:
                    silence_frames += 1
                
                # If user was speaking and now silent for threshold
                if is_speaking and silence_frames > silence_frames_threshold:
                    logger.info("Silence detected. Processing audio...")
                    processing = True
                    is_speaking = False
                    silence_frames = 0
                    
                    # Save accumulated audio to wav file for Groq STT
                    audio_bytes = bytes(audio_buffer)
                    audio_buffer.clear()
                    
                    # Process asynchronously so we don't block the loop entirely
                    asyncio.create_task(
                        process_and_respond(
                            websocket, stream_sid, audio_bytes, agent_id, conv_id, agent_manager
                        )
                    )
                    
            elif msg["event"] == "stop":
                logger.info(f"Stream stopped: {stream_sid}")
                break
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        stream_manager.disconnect(websocket)

async def process_and_respond(
    websocket: WebSocket, 
    stream_sid: str, 
    audio_bytes: bytes, 
    agent_id: str, 
    conv_id: str,
    agent_manager: AgentManager
):
    """
    Converts audio to wav, runs STT, queries agent, and streams TTS back.
    """
    temp_wav = f"temp_{uuid.uuid4().hex}.wav"
    try:
        # Write mu-law to a WAV file that ffmpeg/whisper can read
        pcm_data = audioop.ulaw2lin(audio_bytes, 2)
        with wave.open(temp_wav, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm_data)
        
        # 1. STT (using our existing AudioService)
        from audio_service import AudioService
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
            
        audio_svc = AudioService(api_key=agent.get("groq_api_key") or settings.GROQ_API_KEY)
        text = audio_svc.transcribe_audio(temp_wav)
        logger.info(f"Transcribed: {text}")
        
        if not text.strip():
            logger.info("Empty transcription, resuming listening")
            return
            
        # 2. Agent Chat
        result = agent_manager.chat(agent_id, text, conv_id, channel="voice")
        answer = result["answer"]
        logger.info(f"Agent response: {answer[:50]}...")
        
        # 3. TTS
        tts = agent_manager._get_tts(agent)
        audio_file_path = await tts.generate_speech(answer, voice_id=agent.get("voice_id", "en-US-AriaNeural"))
        
        # 4. Stream Audio Back to Twilio
        # We need to convert the mp3 to 8000Hz mu-law format
        import subprocess
        mulaw_file = f"temp_{uuid.uuid4().hex}.mulaw"
        
        # Use ffmpeg to convert to mu-law 8000Hz
        subprocess.run([
            "ffmpeg", "-i", audio_file_path, 
            "-f", "mulaw", "-ar", "8000", "-ac", "1", mulaw_file,
            "-y"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(mulaw_file, "rb") as f:
            mulaw_data = f.read()
            
        # Send back in chunks to Twilio
        chunk_size = 4000 # 0.5 seconds of audio per chunk
        for i in range(0, len(mulaw_data), chunk_size):
            chunk = mulaw_data[i:i+chunk_size]
            payload = base64.b64encode(chunk).decode("utf-8")
            
            response_msg = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload
                }
            }
            try:
                await websocket.send_text(json.dumps(response_msg))
            except:
                break
            # Slight delay to simulate real-time streaming and not overflow buffer
            await asyncio.sleep(0.4) 
            
        # Cleanup
        os.remove(audio_file_path)
        os.remove(mulaw_file)
        
    except Exception as e:
        logger.error(f"Error processing audio stream: {e}")
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
