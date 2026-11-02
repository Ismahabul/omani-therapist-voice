import os
import re
import time
import logging
from collections import OrderedDict
from typing import Dict, List, Optional
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, field_validator

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("omani-therapist")

# --- Initial Setup ---
load_dotenv()

app = FastAPI(
    title="OMANI-Therapist-Voice API",
    description="A voice-only mental health companion chatbot in Omani Arabic.",
    version="1.0.0"
)

# --- Security Headers Middleware ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# --- CORS Middleware ---
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static files (for script.js)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates directory (for index.html)
templates = Jinja2Templates(directory="templates")

# Initialize LangChain ChatOpenAI Model
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    logger.warning("OPENAI_API_KEY is not set in the environment. Set it in .env for live generation.")

chat_model = ChatOpenAI(
    model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o"),
    temperature=0.7,
    max_tokens=150,
    api_key=openai_api_key if openai_api_key else "placeholder"
)

# --- Pydantic Models ---
class UserInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="The transcribed user speech input.")
    session_id: Optional[str] = Field("default", description="Optional session identifier for chat history isolation.")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Text input cannot be empty or only whitespace.")
        return cleaned


class ResetSessionRequest(BaseModel):
    session_id: Optional[str] = Field("default", description="The session identifier to reset.")


# --- Prompts and Constants ---
SYSTEM_PROMPT = """
You are "Elile" (إكليل), an empathetic, culturally sensitive AI therapist.
Your purpose is to provide mental health support to users in Oman, speaking exclusively in the Omani Arabic dialect.

**Core Directives:**
1. **Language:** You MUST respond ONLY in Omani Arabic. Use authentic Omani vocabulary, grammar, idioms, and conversational markers (e.g., "أهلاً وسهلاً", "كيف حالك اليوم؟", "حاس بيك", "الله يعطيك العافية", "فضفض لي", "ما عليك شر"). Do not switch to Modern Standard Arabic (Fus'ha) or English unless translating or explaining a medical term.
2. **Persona:** You are warm, non-judgmental, patient, and deeply culturally aware of Omani society and traditions. You practice active listening and reflection.
3. **Role:** You are a supportive chatbot, NOT a licensed psychiatrist or medical professional. Never diagnose illnesses or prescribe medication.

**Safety Protocol (Non-Negotiable):**
- If the user expresses suicidal thoughts, self-harm, severe harm to others, or an immediate mental health emergency:
  - Immediately respond with empathy in Omani Arabic and advise them to seek emergency assistance.
  - Inform them of the Oman mental health helpline:
    "سلامتك وصحتك هي أهم شي الحين. أرجوك تواصل فوراً مع الخط الساخن للصحة النفسية في عُمان على الرقم 24601999 أو طوارئ الشرطة على 9999 للمساعدة الفورية. لست وحدك."
  - Do NOT continue therapeutic exploration after triggering the crisis safety response.

**Conversation Flow:**
- Start with a warm, welcoming Omani greeting.
- Use active listening: validate feelings and encourage open expression.
- Keep responses concise, warm, and natural for real-time speech (<20 seconds spoken length, max 2-3 sentences).
"""

CRISIS_KEYWORDS = [
    "kill myself",
    "suicide",
    "end my life",
    "ما اريد اعيش",
    "ما أريد أعيش",
    "اقتل نفسي",
    "أقتل نفسي",
    "انتحار",
    "ابى اموت",
    "أبى أموت",
    "بموت",
    "اريد اموت",
    "أريد أموت",
    "انهي حياتي",
    "أنهي حياتي"
]

CRISIS_RESPONSE_ARABIC = (
    "حاس بضيقك وألمك، وصحتك وسلامتك هي أهم شي الحين. "
    "أرجوك تواصل فوراً مع خط الاستشارات النفسية بوزارة الصحة في عُمان على الرقم 24601999 "
    "أو طوارئ الشرطة على 9999 للحصول على مساعدة عاجلة. لست وحدك."
)

FALLBACK_ERROR_ARABIC = (
    "أنا آسف، صار عندي خلل بسيط في الاتصال الحين. نقدر نحاول مرة ثانية بعد شوي؟"
)

# In-memory session store (bounded history per session)
MAX_HISTORY_MESSAGES = 12
sessions_store: Dict[str, List[BaseMessage]] = {}


def get_session_history(session_id: str) -> List[BaseMessage]:
    """Retrieve or initialize conversation history for a given session."""
    if session_id not in sessions_store:
        sessions_store[session_id] = [SystemMessage(content=SYSTEM_PROMPT)]
    return sessions_store[session_id]


def append_and_trim_history(session_id: str, message: BaseMessage) -> None:
    """Append a message and keep history within context limits."""
    history = get_session_history(session_id)
    history.append(message)
    # Keep the initial SystemMessage and the latest MAX_HISTORY_MESSAGES
    if len(history) > MAX_HISTORY_MESSAGES + 1:
        sessions_store[session_id] = [history[0]] + history[-MAX_HISTORY_MESSAGES:]


# --- API Endpoints ---

@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Health check endpoint for deployment monitoring."""
    return {"status": "ok", "app": "OMANI-Therapist-Voice", "version": "1.0.0"}


@app.get("/", response_class=HTMLResponse)
async def get_chat_interface(request: Request):
    """Serve the main HTML chat interface."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/reset", response_class=JSONResponse)
async def reset_session(req: ResetSessionRequest):
    """Reset conversation history for the specified session."""
    sid = req.session_id or "default"
    sessions_store[sid] = [SystemMessage(content=SYSTEM_PROMPT)]
    logger.info(f"Session '{sid}' conversation history reset.")
    return {"status": "reset", "session_id": sid}


@app.post("/process-audio", response_class=JSONResponse)
async def process_audio(user_input: UserInput):
    """
    Main endpoint to handle STT text input -> Safety Check -> LLM Generation -> Response.
    """
    user_text = user_input.text
    session_id = user_input.session_id or "default"
    logger.info(f"Session [{session_id}] User said: {user_text}")

    # 1. Safety Layer (Crisis keywords check)
    user_text_lower = user_text.lower()
    if any(keyword in user_text_lower for keyword in CRISIS_KEYWORDS):
        logger.warning(f"Session [{session_id}] CRISIS DETECTED: {user_text}")
        append_and_trim_history(session_id, HumanMessage(content=user_text))
        append_and_trim_history(session_id, AIMessage(content=CRISIS_RESPONSE_ARABIC))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "reply": CRISIS_RESPONSE_ARABIC,
                "is_crisis": True,
                "session_id": session_id
            }
        )

    # 2. Add user message to history
    append_and_trim_history(session_id, HumanMessage(content=user_text))
    current_history = get_session_history(session_id)

    # 3. Model Response Generation with LangChain ChatOpenAI
    try:
        response = await chat_model.ainvoke(current_history)
        ai_response_text = response.content
        if not isinstance(ai_response_text, str):
            ai_response_text = str(ai_response_text)
        
        # Add AI response to conversation history
        append_and_trim_history(session_id, AIMessage(content=ai_response_text))
        logger.info(f"Session [{session_id}] Elile replied: {ai_response_text}")

        return JSONResponse(content={
            "reply": ai_response_text,
            "is_crisis": False,
            "session_id": session_id
        })

    except Exception as e:
        logger.error(f"Error calling ChatOpenAI for session [{session_id}]: {e}", exc_info=True)
        # Note: We do not add the technical error to conversational memory
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "reply": FALLBACK_ERROR_ARABIC,
                "is_crisis": False,
                "session_id": session_id,
                "warning": "model_unavailable"
            }
        )


if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
