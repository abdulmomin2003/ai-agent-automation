import os
import uuid
import tempfile
import logging
from typing import Optional
import edge_tts
from groq import Groq

from config import settings

logger = logging.getLogger(__name__)

class AudioService:
    """
    Handles Speech-to-Text (via Groq Whisper) and Text-to-Speech (via edge-tts).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        if not self.api_key:
            logger.warning("Groq API key missing. STT will fail.")
        else:
            self.groq_client = Groq(api_key=self.api_key)

        # Ensure a directory for temp audio exists
        self.audio_dir = os.path.join(settings.UPLOAD_DIR, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)

    async def generate_speech(self, text: str, voice: str = "en-US-AriaNeural") -> str:
        """
        Converts text to speech using edge-tts (free, realistic Microsoft voices).
        Returns the path to the generated MP3 file.
        """
        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        output_path = os.path.join(self.audio_dir, file_name)

        # Remove markdown symbols for better speech
        clean_text = text.replace("*", "").replace("#", "").replace("_", "")

        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(output_path)
        
        logger.info(f"Generated TTS audio: {output_path}")
        return output_path

    def transcribe_audio(self, audio_path: str) -> str:
        """
        Transcribes an audio file using Groq's high-speed Whisper model.
        """
        if not self.groq_client:
            raise ValueError("Groq API key not configured")

        logger.info(f"Transcribing audio: {audio_path}")
        
        with open(audio_path, "rb") as file:
            transcription = self.groq_client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), file.read()),
                model="whisper-large-v3",
                response_format="json",
            )
        
        text = transcription.text
        logger.info(f"Transcription complete: '{text[:50]}...'")
        return text

    def clean_up(self, file_path: str):
        """Helper to remove temp audio files."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Failed to clean up {file_path}: {e}")
