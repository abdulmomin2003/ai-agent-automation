"""
Twilio Voice service — handles inbound calls, TwiML generation,
and call forwarding.

Call Flow:
  1. Phone rings → Twilio POST /twilio/voice/inbound
  2. TwiML: Greet → Gather speech input
  3. Speech input → STT (Groq) → RAG query → TTS → Play response
  4. Loop until caller hangs up or agent forwards call
"""

import logging
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from config import settings

logger = logging.getLogger(__name__)


def build_gather_twiml(
    greeting: str = None,
    action_url: str = "/twilio/voice/respond",
    voice: str = "Polly.Joanna",
    language: str = "en-US",
) -> str:
    """
    Build TwiML that greets the caller and gathers speech input.

    Args:
        greeting: Text to say before listening. If None, skips greeting.
        action_url: URL to POST the transcribed speech to.
        voice: Twilio <Say> voice.
        language: Speech recognition language.

    Returns:
        TwiML XML string.
    """
    response = Element("Response")

    if greeting:
        say = SubElement(response, "Say", voice=voice)
        say.text = greeting

    gather = SubElement(
        response, "Gather",
        input="speech",
        action=action_url,
        method="POST",
        speechTimeout="auto",
        language=language,
    )
    gather_say = SubElement(gather, "Say", voice=voice)
    gather_say.text = "I'm listening."

    # If no input, prompt again
    redirect = SubElement(response, "Redirect")
    redirect.text = action_url.replace("/respond", "/inbound")

    return '<?xml version="1.0" encoding="UTF-8"?>' + tostring(response, encoding="unicode")


def build_say_and_gather_twiml(
    text: str,
    action_url: str = "/twilio/voice/respond",
    voice: str = "Polly.Joanna",
    language: str = "en-US",
) -> str:
    """
    Build TwiML that says a response and then gathers the next speech input.
    Used for the conversational loop.
    """
    response = Element("Response")

    gather = SubElement(
        response, "Gather",
        input="speech",
        action=action_url,
        method="POST",
        speechTimeout="auto",
        language=language,
    )
    gather_say = SubElement(gather, "Say", voice=voice)
    gather_say.text = text

    # If no further input, say goodbye
    say_bye = SubElement(response, "Say", voice=voice)
    say_bye.text = "Thank you for calling. Goodbye!"
    SubElement(response, "Hangup")

    return '<?xml version="1.0" encoding="UTF-8"?>' + tostring(response, encoding="unicode")


def build_forward_twiml(
    forward_number: str,
    message: str = "Please hold while I transfer your call.",
    voice: str = "Polly.Joanna",
) -> str:
    """
    Build TwiML that announces a transfer and forwards the call.
    """
    response = Element("Response")

    say = SubElement(response, "Say", voice=voice)
    say.text = message

    dial = SubElement(response, "Dial")
    number = SubElement(dial, "Number")
    number.text = forward_number

    return '<?xml version="1.0" encoding="UTF-8"?>' + tostring(response, encoding="unicode")


def build_hangup_twiml(
    message: str = "Thank you for calling. Goodbye!",
    voice: str = "Polly.Joanna",
) -> str:
    """Build TwiML that says goodbye and hangs up."""
    response = Element("Response")

    say = SubElement(response, "Say", voice=voice)
    say.text = message

    SubElement(response, "Hangup")

    return '<?xml version="1.0" encoding="UTF-8"?>' + tostring(response, encoding="unicode")


def detect_intent(text: str) -> str:
    """
    Simple intent detection from user speech.

    Returns one of: 'forward', 'hangup', 'continue'
    """
    text_lower = text.lower().strip()

    forward_phrases = [
        "transfer me", "speak to a human", "talk to someone",
        "forward my call", "connect me to", "real person",
        "speak to a person", "human agent", "representative",
        "talk to a real", "let me speak", "can i talk to",
    ]
    hangup_phrases = [
        "goodbye", "bye", "hang up", "that's all",
        "thank you bye", "no more questions", "i'm done",
        "end call", "nothing else",
    ]

    for phrase in forward_phrases:
        if phrase in text_lower:
            return "forward"

    for phrase in hangup_phrases:
        if phrase in text_lower:
            return "hangup"

    return "continue"
