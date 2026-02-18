import os
import io
import random
from groq import Groq
from prompts import SYSTEM_PROMPTS, CONVERSATION_STARTERS

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    transcription = client.audio.transcriptions.create(
        file=audio_file,
        model="whisper-large-v3",
        language="en",
        response_format="text"
    )
    return transcription.strip()


def get_ai_response(user_message: str, level: str, conversation_history: list, exchange_count: int) -> str:
    system_prompt = SYSTEM_PROMPTS.get(level, SYSTEM_PROMPTS["intermediate"])
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": user_message})

    model = "llama-3.3-70b-versatile"
    if level == "beginner":
        model = "gemma2-9b-it"

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=300,
        temperature=0.8,
    )
    return response.choices[0].message.content


def text_to_speech(text: str, level: str, gender: str = "male") -> bytes:
    # Male voices
    male_voices = {
        "beginner":     "Charon-PlayAI",
        "intermediate": "Atlas-PlayAI",
        "advanced":     "Orion-PlayAI",
    }
    # Female voices
    female_voices = {
        "beginner":     "Celeste-PlayAI",
        "intermediate": "Aoede-PlayAI",
        "advanced":     "Leda-PlayAI",
    }

    voices = female_voices if gender == "female" else male_voices
    voice = voices.get(level, "Atlas-PlayAI")

    # Remove feedback section from TTS
    speak_text = text
    if "FEEDBACK_START" in text:
        speak_text = text.split("FEEDBACK_START")[0].strip()

    response = client.audio.speech.create(
        model="playai-tts",
        voice=voice,
        input=speak_text,
        response_format="wav"
    )
    return response.read()


def get_conversation_starter(level: str) -> str:
    starters = CONVERSATION_STARTERS.get(level, CONVERSATION_STARTERS["intermediate"])
    return random.choice(starters)


def generate_session_summary(conversation_history: list, level: str) -> str:
    if len(conversation_history) < 2:
        return "Session too short for detailed feedback."

    conv_text = "\n".join([
        f"USER: {msg['content']}"
        for msg in conversation_history
        if msg["role"] == "user"
    ])

    prompt = f"""Analyze this English speaking session for a {level} level student.

Student messages:
{conv_text}

Give a structured summary:
1. Overall Score: X/10
2. Strengths (2-3 points)
3. Areas to Improve (2-3 points)
4. Grammar Issues (with corrections)
5. Vocabulary Tips
6. Next Session Goal

Be encouraging and constructive."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7,
    )
    return response.choices[0].message.content