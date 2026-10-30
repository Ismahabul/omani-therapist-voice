import os
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
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
    description="A voice-only mental health chatbot using Omani Arabic.",
    version="1.0.0"
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
    model="gpt-4o",
    temperature=0.7,
    max_tokens=150,
    api_key=openai_api_key if openai_api_key else "placeholder"
)

# --- System Prompt Definition ---
SYSTEM_PROMPT = """
You are 'Elile', a compassionate, culturally sensitive, and empathetic AI mental health companion.
Your primary role is to provide a safe, supportive, and non-judgmental space for users to express their thoughts and feelings.
You communicate EXCLUSIVELY in the Omani Arabic dialect.

**Core Directives:**
1.  **Language:** Speak ONLY in conversational, natural Omani Arabic. Avoid Modern Standard Arabic (MSA) unless absolutely necessary for clarity, but prioritize Omani phrasing, idioms, and colloquialisms. (e.g., use words like 'مو حالك', 'زين', 'واجد', 'تو', 'هيش', 'شخبارك').
2.  **Persona:** You are a supportive companion, NOT a licensed human therapist. Always maintain this boundary gently. Your tone must be warm, patient, kind, and validating.
3.  **Safety First (Critical Protocol):**
    *   If the user expresses ANY thoughts of suicide, self-harm, harm to others, or severe abuse, you MUST immediately intervene.
    *   Acknowledge their pain with deep empathy.
    *   State clearly and kindly in Omani Arabic that you are an AI and their safety is the top priority.
    *   Provide the Oman national mental health support line (Al Masarra / Ministry of Health helpline: 24601999 or Emergency: 9999).
    *   Do not continue therapeutic exploration once the crisis protocol is triggered.
4.  **Conversation Flow:**
    *   Start with a warm, welcoming Omani greeting.
    *   Use active listening: reflect feelings, validate emotional distress.
    *   Keep responses concise (<20 seconds when spoken aloud) to maintain an engaging spoken dialogue.
"""

# Crisis response in Omani/Gulf Arabic with real helpline numbers
CRISIS_RESPONSE_ARABIC = (
    "حاس بضيقك وألمك، وصحتك وسلامتك هي أهم شي عندي. أنا مجرد رفيق ذكاء اصطناعي وما أقدر أساعدك في هذا الموقف الصعب. "
    "أرجوك تواصل فوراً مع خط الاستشارات النفسية بوزارة الصحة في عُمان على الرقم 24601999 أو طوارئ الشرطة على 9999 للمساعدة الفورية. لست وحدك."
)

FALLBACK_ERROR_ARABIC = (
    "أنا آسف، صار عندي خلل بسيط في الاتصال الحين. نقدر نحاول مرة ثانية بعد شوي؟"
)

CRISIS_KEYWORDS = [
    "kill myself", "suicide", "end my life", "want to die",
    "انتحار", "اقتل نفسي", "ما اريد اعيش", "اريد اموت", "ابى اموت",
    "بموت", "انهي حياتي", "ما ابغى اعيش"
]

# In-memory session store (POC level; persistent store in production)
# Structure: { session_id: [SystemMessage, HumanMessage, AIMessage, ...] }
sessions: Dict[str, List[BaseMessage]] = {}
MAX_SESSION_HISTORY_MESSAGES = 12


def get_session_history(session_id: str) -> List[BaseMessage]:
    """Retrieve or initialize conversation history for a given session."""
    if session_id not in sessions:
        sessions[session_id] = [SystemMessage(content=SYSTEM_PROMPT)]
    return sessions[session_id]


def append_and_trim_history(session_id: str, message: BaseMessage) -> None:
    """Append a message and ensure history does not exceed maximum length."""
    history = get_session_history(session_id)
    history.append(message)
    # Keep SystemMessage + last N messages
    if len(history) > (MAX_SESSION_HISTORY_MESSAGES + 1):
        sessions[session_id] = [history[0]] + history[-MAX_SESSION_HISTORY_MESSAGES:]


# --- Pydantic Models ---
class UserInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=1500, description="The transcribed speech text from the user.")
    session_id: Optional[str] = Field("default", description="Unique session identifier for the user.")

    @field_validator("text")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Text input cannot be empty or only whitespace.")
        return stripped


class ResetRequest(BaseModel):
    session_id: Optional[str] = Field("default", description="Session identifier to reset.")


# --- API Endpoints ---

@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Health check endpoint for monitoring."""
    return JSONResponse(content={
        "status": "healthy",
        "service": "OMANI-Therapist-Voice",
        "version": "1.0.0"
    })


@app.get("/", response_class=HTMLResponse)
async def get_chat_interface(request: Request):
    """Serve the main HTML chat interface."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/reset", response_class=JSONResponse)
async def reset_session(reset_req: ResetRequest):
    """Reset the conversation history for a given session."""
    session_id = reset_req.session_id or "default"
    sessions[session_id] = [SystemMessage(content=SYSTEM_PROMPT)]
    logger.info(f"Session [{session_id}] has been reset.")
    return JSONResponse(content={
        "status": "reset_success",
        "session_id": session_id
    })


@app.post("/process-audio", response_class=JSONResponse)
async def process_audio(user_input: UserInput):
    """
    Main endpoint to handle STT text -> LLM -> Response pipeline.
    """
    user_text = user_input.text
    session_id = user_input.session_id or "default"
    logger.info(f"Session [{session_id}] user said: {user_text}")

    # 1. Safety & Crisis Layer Check
    lower_text = user_text.lower()
    if any(keyword in lower_text for keyword in CRISIS_KEYWORDS):
        logger.warning(f"CRISIS DETECTED for session [{session_id}]!")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "reply": CRISIS_RESPONSE_ARABIC,
                "is_crisis": True,
                "session_id": session_id
            }
        )

    # 2. Add user message to session history
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