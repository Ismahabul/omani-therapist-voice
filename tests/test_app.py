import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app import (
    app,
    get_session_history,
    sessions_store,
    CRISIS_RESPONSE_ARABIC,
    FALLBACK_ERROR_ARABIC,
    SYSTEM_PROMPT
)

client = TestClient(app)


def setup_function():
    """Clear in-memory session store before each test."""
    sessions_store.clear()


def test_health_check():
    """Verify health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "OMANI-Therapist-Voice"


def test_home_page_serves_html():
    """Verify the root endpoint serves the Arabic RTL HTML interface."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html_content = response.text
    assert "dir=\"rtl\"" in html_content
    assert "إكليل" in html_content
    assert "recordBtn" in html_content
    assert "24601999" in html_content


def test_validation_empty_or_whitespace_input():
    """Verify empty or whitespace-only text inputs are rejected with 422."""
    res_empty = client.post("/process-audio", json={"text": ""})
    assert res_empty.status_code == 422

    res_whitespace = client.post("/process-audio", json={"text": "    "})
    assert res_whitespace.status_code == 422


def test_crisis_detection_english():
    """Verify crisis detection on English suicidal phrasing."""
    payload = {
        "text": "I feel like I want to commit suicide and end my life",
        "session_id": "test_crisis_en"
    }
    response = client.post("/process-audio", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_crisis"] is True
    assert data["reply"] == CRISIS_RESPONSE_ARABIC
    assert "24601999" in data["reply"]


def test_crisis_detection_arabic():
    """Verify crisis detection on Omani Arabic crisis phrasing."""
    payload = {
        "text": "تعبان وايد وما اريد اعيش خلاص",
        "session_id": "test_crisis_ar"
    }
    response = client.post("/process-audio", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_crisis"] is True
    assert data["reply"] == CRISIS_RESPONSE_ARABIC


@pytest.mark.asyncio
async def test_successful_llm_response():
    """Verify standard conversation flow with mocked LLM."""
    mock_reply = "أهلاً وسهلاً بك، سلامتك وما تشوف شر. خبرني شو مضايقك؟"
    
    with patch("app.chat_model.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = AIMessage(content=mock_reply)
        
        payload = {
            "text": "السلام عليكم، حاس بضيق وتوتر اليوم",
            "session_id": "session_success"
        }
        response = client.post("/process-audio", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == mock_reply
        assert data["is_crisis"] is False
        assert data["session_id"] == "session_success"

        # Verify conversation history was updated
        history = get_session_history("session_success")
        assert len(history) == 3  # System, Human, AI
        assert isinstance(history[1], HumanMessage)
        assert history[1].content == "السلام عليكم، حاس بضيق وتوتر اليوم"
        assert isinstance(history[2], AIMessage)
        assert history[2].content == mock_reply


@pytest.mark.asyncio
async def test_llm_failure_graceful_fallback():
    """Verify system handles API errors gracefully without crashing or polluting history."""
    with patch("app.chat_model.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.side_effect = Exception("OpenAI API rate limit or outage")
        
        payload = {
            "text": "كيف أقدر أرتاح وأهدأ؟",
            "session_id": "session_error"
        }
        response = client.post("/process-audio", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == FALLBACK_ERROR_ARABIC
        assert data["warning"] == "model_unavailable"

        # Verify history only has the user message, NOT the error fallback
        history = get_session_history("session_error")
        assert len(history) == 2  # System, Human only


def test_session_reset():
    """Verify reset endpoint clears history back to just the system prompt."""
    sid = "session_to_reset"
    # Seed some history
    history = get_session_history(sid)
    history.append(HumanMessage(content="مرحبا"))
    history.append(AIMessage(content="أهلا وسهلا"))
    assert len(get_session_history(sid)) == 3

    # Reset
    response = client.post("/reset", json={"session_id": sid})
    assert response.status_code == 200
    assert response.json()["status"] == "reset"

    new_history = get_session_history(sid)
    assert len(new_history) == 1
    assert isinstance(new_history[0], SystemMessage)


def test_session_isolation():
    """Verify different sessions do not leak conversation histories into each other."""
    client.post("/process-audio", json={"text": "أنا مستخدم أ", "session_id": "user_a"})
    client.post("/process-audio", json={"text": "أنا مستخدم ب", "session_id": "user_b"})

    history_a = get_session_history("user_a")
    history_b = get_session_history("user_b")

    user_a_texts = [m.content for m in history_a if isinstance(m, HumanMessage)]
    user_b_texts = [m.content for m in history_b if isinstance(m, HumanMessage)]

    assert "أنا مستخدم أ" in user_a_texts
    assert "أنا مستخدم أ" not in user_b_texts
    assert "أنا مستخدم ب" in user_b_texts
    assert "أنا مستخدم ب" not in user_a_texts
