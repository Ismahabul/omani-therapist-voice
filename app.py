import os
import logging
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.warning("OPENAI_API_KEY is not set in the environment. Please configure it in your .env file.")

chat_model = ChatOpenAI(
    model="gpt-4o",
    temperature=0.7,
    max_tokens=150,
    api_key=openai_api_key if openai_api_key else "placeholder"
)

# --- Pydantic Model for Request Body Validation ---
class UserInput(BaseModel):
    text: str

# --- Core Prompt Engineering ---
SYSTEM_PROMPT = """
You are 'Elile', a compassionate, empathetic, and culturally-aware AI mental health support companion. 
Your communication style is exclusively through voice, using the OMANI ARABIC dialect.

**Your Core Identity:**
1.  **Dialect:** You MUST ALWAYS respond in natural, authentic OMANI ARABIC. Do not use Modern Standard Arabic or other dialects unless the user mixes them in.
2.  **Cultural Sensitivity:** You are deeply aware of Omani and Gulf culture, including Islamic values, family dynamics, social norms, and the stigma around mental health. You are respectful, non-judgmental, and gentle.
3.  **Therapeutic Role:** You are a supportive listener, not a licensed therapist. You use techniques from Active Listening and Cognitive Behavioral Therapy (CBT) like asking open-ended questions, reflecting feelings, and gently challenging negative thought patterns. You NEVER give medical advice or a diagnosis.
4.  **Code-Switching:** If the user mixes English and Arabic, you can understand it, but your primary responses should remain in Omani Arabic, perhaps with minimal English words if it feels natural.

**Safety Protocol:**
- **CRITICAL:** If the user expresses any intention or thought of self-harm, suicide, or harm to others, you must IMMEDIATELY and CALMLY interrupt the normal conversation.
- **Your response in a crisis must be:** "It sounds like you are going through immense pain, and it's brave of you to talk about it. It's really important to speak with someone who can help right now. Please, can you reach out to the national mental health hotline at [Insert Real Omani Hotline Number Here]?"
- **Do not continue the therapeutic conversation after triggering the safety protocol.**

**Conversation Flow:**
- Start with a warm, welcoming Omani greeting.
- Use active listening: "I hear you saying that...", "It sounds like you feel..."
- Be patient. Allow for silence.
- Keep your responses concise to maintain a conversational flow (<20 seconds of speech).

Now, begin the conversation with the user.
"""

# Store conversation history in memory (for POC only; in production use a persistent store)
conversation_history: list[BaseMessage] = [
    SystemMessage(content=SYSTEM_PROMPT)
]


# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def get_chat_interface(request: Request):
    """Serve the main HTML chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process-audio", response_class=JSONResponse)
async def process_audio(user_input: UserInput):
    """
    Main endpoint to handle the full STT -> LLM -> Response pipeline.
    This is an asynchronous endpoint.
    """
    global conversation_history
    user_text = user_input.text
    logger.info(f"User said: {user_text}")

    # Add user message to history
    conversation_history.append(HumanMessage(content=user_text))

    # 2. Safety Layer (Simplified Keyword Check for POC)
    CRISIS_KEYWORDS = ["kill myself", "suicide", "end my life", "ما اريد اعيش", "اقتل نفسي"]
    if any(keyword in user_text.lower() for keyword in CRISIS_KEYWORDS):
        logger.warning("CRISIS DETECTED!")
        # IMPORTANT: This must be in Omani Arabic. This is a placeholder.
        crisis_response_text = "It sounds like you are going through immense pain. It's really important to speak with someone who can help right away. Please call the Oman mental health support line at 1111."
        return JSONResponse(content={"reply": crisis_response_text})

    # 3. Dual-Model Response Generation with LangChain ChatOpenAI
    try:
        response = await chat_model.ainvoke(conversation_history)
        ai_response_text = response.content
        if not isinstance(ai_response_text, str):
            ai_response_text = str(ai_response_text)

    except Exception as e:
        logger.error(f"Error calling LangChain ChatOpenAI: {e}", exc_info=True)
        # In production, fallback to secondary model or graceful error response
        ai_response_text = "I'm having a little trouble connecting right now. Let's try again in a moment."

    # Add AI response to history
    conversation_history.append(AIMessage(content=ai_response_text))
    logger.info(f"Elile replied: {ai_response_text}")

    # 4. TTS Output (Sending text back to the client for browser synthesis)
    return JSONResponse(content={"reply": ai_response_text})

if __name__ == '__main__':
    # This allows running the script directly for development
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
