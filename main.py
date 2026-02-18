import os
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq_service import (
    transcribe_audio,
    get_ai_response,
    text_to_speech,
    get_conversation_starter,
    generate_session_summary
)

load_dotenv()

app = FastAPI(title="Speaking Partner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}


class StartSessionRequest(BaseModel):
    user_id: str
    level: str
    gender: str = "male"


class TextMessageRequest(BaseModel):
    session_id: str
    message: str


class EndSessionRequest(BaseModel):
    session_id: str


@app.post("/session/start")
async def start_session(req: StartSessionRequest):
    if req.level not in ["beginner", "intermediate", "advanced"]:
        raise HTTPException(status_code=400, detail="Invalid level")
    if req.gender not in ["male", "female"]:
        raise HTTPException(status_code=400, detail="Invalid gender")

    session_id = str(uuid.uuid4())
    starter = get_conversation_starter(req.level)

    sessions[session_id] = {
        "user_id": req.user_id,
        "level": req.level,
        "gender": req.gender,
        "history": [{"role": "assistant", "content": starter}],
        "exchange_count": 0,
        "stats": {
            "total_words": 0,
            "grammar_errors": 0,
            "scores": [],
            "duration_seconds": 0,
        }
    }

    audio_bytes = text_to_speech(starter, req.level, req.gender)

    return {
        "session_id": session_id,
        "message": starter,
        "audio_hex": audio_bytes.hex(),
    }


@app.post("/session/voice")
async def process_voice(
    session_id: str = Form(...),
    audio: UploadFile = File(...)
):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    audio_bytes = await audio.read()

    try:
        user_text = transcribe_audio(audio_bytes, audio.filename or "audio.webm")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT Error: {str(e)}")

    if not user_text:
        raise HTTPException(status_code=400, detail="Could not transcribe audio")

    # Update stats
    word_count = len(user_text.split())
    session["stats"]["total_words"] += word_count
    session["exchange_count"] += 1

    ai_response = get_ai_response(
        user_text,
        session["level"],
        session["history"],
        session["exchange_count"]
    )

    # Parse score from feedback if present
    if "FEEDBACK_START" in ai_response and "Score:" in ai_response:
        try:
            score_line = [l for l in ai_response.split("\n") if "Score:" in l][0]
            score = float(score_line.split(":")[1].strip().split("/")[0])
            session["stats"]["scores"].append(score)
        except Exception:
            pass

    session["history"].append({"role": "user", "content": user_text})
    session["history"].append({"role": "assistant", "content": ai_response})

    try:
        audio_response = text_to_speech(ai_response, session["level"], session["gender"])
        audio_hex = audio_response.hex()
    except Exception:
        audio_hex = None

    avg_score = round(sum(session["stats"]["scores"]) / len(session["stats"]["scores"]), 1) if session["stats"]["scores"] else None

    return {
        "user_text": user_text,
        "ai_response": ai_response,
        "audio_hex": audio_hex,
        "exchange_count": session["exchange_count"],
        "stats": {
            "total_words": session["stats"]["total_words"],
            "exchanges": session["exchange_count"],
            "avg_score": avg_score,
        }
    }


@app.post("/session/text")
async def process_text(req: TextMessageRequest):
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[req.session_id]
    session["exchange_count"] += 1
    session["stats"]["total_words"] += len(req.message.split())

    ai_response = get_ai_response(
        req.message,
        session["level"],
        session["history"],
        session["exchange_count"]
    )

    if "FEEDBACK_START" in ai_response and "Score:" in ai_response:
        try:
            score_line = [l for l in ai_response.split("\n") if "Score:" in l][0]
            score = float(score_line.split(":")[1].strip().split("/")[0])
            session["stats"]["scores"].append(score)
        except Exception:
            pass

    session["history"].append({"role": "user", "content": req.message})
    session["history"].append({"role": "assistant", "content": ai_response})

    try:
        audio_response = text_to_speech(ai_response, session["level"], session["gender"])
        audio_hex = audio_response.hex()
    except Exception:
        audio_hex = None

    avg_score = round(sum(session["stats"]["scores"]) / len(session["stats"]["scores"]), 1) if session["stats"]["scores"] else None

    return {
        "ai_response": ai_response,
        "audio_hex": audio_hex,
        "exchange_count": session["exchange_count"],
        "stats": {
            "total_words": session["stats"]["total_words"],
            "exchanges": session["exchange_count"],
            "avg_score": avg_score,
        }
    }


@app.post("/session/end")
async def end_session(req: EndSessionRequest):
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[req.session_id]
    summary = generate_session_summary(session["history"], session["level"])
    final_stats = session["stats"]
    final_stats["avg_score"] = round(sum(final_stats["scores"]) / len(final_stats["scores"]), 1) if final_stats["scores"] else 0

    del sessions[req.session_id]
    return {"summary": summary, "stats": final_stats}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)