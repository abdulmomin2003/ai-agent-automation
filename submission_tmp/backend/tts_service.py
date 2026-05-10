"""
Unified Text-to-Speech service.

Supports:
- ElevenLabs (premium, natural voices) — if API key provided
- Edge-TTS (free, Microsoft voices) — default fallback
"""

import os
import uuid
import logging
from typing import Optional

import edge_tts
import httpx

from config import settings

logger = logging.getLogger(__name__)


class TTSService:
    """
    Generates speech audio from text.

    Priority:
    1. ElevenLabs (if api_key provided)
    2. Edge-TTS (always available, free)
    """

    def __init__(self, elevenlabs_api_key: Optional[str] = None):
        self.elevenlabs_key = elevenlabs_api_key
        self.audio_dir = os.path.join(settings.UPLOAD_DIR, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)

        if self.elevenlabs_key and self.elevenlabs_key != "your-key":
            logger.info("ElevenLabs TTS enabled")
        else:
            self.elevenlabs_key = None
            logger.info("Using Edge-TTS (free fallback)")

    def _clean_text(self, text: str) -> str:
        """Remove markdown formatting for cleaner speech."""
        return text.replace("*", "").replace("#", "").replace("_", "").replace("`", "")

    async def generate_speech(
        self,
        text: str,
        voice_id: str = "en-US-AriaNeural",
        use_elevenlabs: bool = True,
    ) -> str:
        """
        Generate speech audio from text.

        Args:
            text: Text to convert to speech.
            voice_id: Voice identifier. For Edge-TTS, use format like 'en-US-AriaNeural'.
                      For ElevenLabs, use the voice ID from their API.
            use_elevenlabs: Whether to attempt ElevenLabs first.

        Returns:
            Path to the generated MP3 file.
        """
        clean_text = self._clean_text(text)

        if not clean_text.strip():
            raise ValueError("No text to convert to speech")

        # Try ElevenLabs first if available and requested
        if use_elevenlabs and self.elevenlabs_key:
            try:
                return await self._elevenlabs_tts(clean_text, voice_id)
            except Exception as e:
                logger.warning("ElevenLabs TTS failed, falling back to Edge-TTS: %s", e)

        # Fallback to Edge-TTS
        return await self._edge_tts(clean_text, voice_id)

    async def _elevenlabs_tts(self, text: str, voice_id: str) -> str:
        """Generate speech via ElevenLabs API."""
        # Default ElevenLabs voice if an Edge-TTS voice name was passed
        if "Neural" in voice_id or "-" in voice_id:
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel" default

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self.elevenlabs_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text[:5000],  # ElevenLabs limit
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        output_path = os.path.join(self.audio_dir, file_name)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

        logger.info("ElevenLabs TTS generated: %s", output_path)
        return output_path

    async def _edge_tts(self, text: str, voice_id: str) -> str:
        """Generate speech via Edge-TTS (free)."""
        # Ensure we have a valid Edge-TTS voice name
        if not voice_id or "Neural" not in voice_id:
            voice_id = "en-US-AriaNeural"

        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        output_path = os.path.join(self.audio_dir, file_name)

        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(output_path)

        logger.info("Edge-TTS generated: %s", output_path)
        return output_path

    async def generate_speech_bytes(
        self,
        text: str,
        voice_id: str = "en-US-AriaNeural",
    ) -> bytes:
        """Generate speech and return raw audio bytes (for streaming to Twilio)."""
        path = await self.generate_speech(text, voice_id)
        try:
            with open(path, "rb") as f:
                return f.read()
        finally:
            # Clean up temp file
            try:
                os.remove(path)
            except OSError:
                pass
