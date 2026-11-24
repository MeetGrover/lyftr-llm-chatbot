import pytest
import os
import json
from pathlib import Path
from fastapi.testclient import TestClient

TEST_DB_PATH = Path("./test_app.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["LLM_API_KEYS"] = "key_1_test,key_2_test"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["MOCK_LLM"] = "true"

from app.main import app
from app.database import init_db

@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
    init_db()
    yield
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] >= 2
    assert data["cache_enabled"] is True

def test_chat_success_and_caching(client):
    session_1 = "s-test-session-1"
    payload = {
        "session_id": session_1,
        "message": "What is the capital of France?"
    }
    
    # 1. First call -> LIVE_INFERENCE
    res1 = client.post("/chat", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["session_id"] == session_1
    assert "Paris" in data1["reply"]
    meta1 = data1["metadata"]
    assert meta1["resolution_source"] == "LIVE_INFERENCE"
    assert meta1["key_id"] == "key_1"
    assert meta1["fallback_attempts"] == 0
    assert meta1["input_tokens"] > 0
    assert meta1["output_tokens"] > 0
    assert isinstance(meta1["latency_ms"], int)

    # 2. Same message in a new session -> LLM_CACHE
    session_2 = "s-test-session-2"
    payload2 = {
        "session_id": session_2,
        "message": "What is the capital of France?"
    }
    res2 = client.post("/chat", json=payload2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["session_id"] == session_2
    assert data2["reply"] == data1["reply"] # Identical reply text
    meta2 = data2["metadata"]
    assert meta2["resolution_source"] == "LLM_CACHE"
    assert meta2["key_id"] is None # null on LLM_CACHE
    assert meta2["fallback_attempts"] == 0 # 0 on LLM_CACHE
    assert meta2["input_tokens"] == meta1["input_tokens"] # Stored tokens
    assert meta2["output_tokens"] == meta1["output_tokens"]

def test_different_message_is_live_inference(client):
    session = "s-diff-test"
    res = client.post("/chat", json={
        "session_id": session,
        "message": "Tell me a joke"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

def test_multi_turn_history(client):
    session = "s-multi-turn"
    
    # First turn
    res1 = client.post("/chat", json={
        "session_id": session,
        "message": "What is the capital of France?"
    })
    assert res1.status_code == 200
    
    # Second turn
    res2 = client.post("/chat", json={
        "session_id": session,
        "message": "What is its population?"
    })
    assert res2.status_code == 200
    
    # Check history endpoint
    hist_res = client.get(f"/sessions/{session}/messages")
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["session_id"] == session
    messages = hist["messages"]
    assert len(messages) == 4 # 2 user, 2 assistant
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is the capital of France?"
    assert messages[1]["role"] == "assistant"
    assert "metadata" in messages[1]
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "What is its population?"
    assert messages[3]["role"] == "assistant"

def test_unknown_session_returns_404(client):
    res = client.get("/sessions/unknown-session-xyz/messages")
    assert res.status_code == 404
    assert res.json() == {"detail": "session not found"}

def test_validation_errors_422(client):
    # Empty message
    res1 = client.post("/chat", json={"session_id": "s-1", "message": "   "})
    assert res1.status_code == 422
    assert "detail" in res1.json()

    # Empty session_id
    res2 = client.post("/chat", json={"session_id": "  ", "message": "hello"})
    assert res2.status_code == 422
    assert "detail" in res2.json()

    # Message over 4000 chars
    long_msg = "x" * 4001
    res3 = client.post("/chat", json={"session_id": "s-1", "message": long_msg})
    assert res3.status_code == 422
    assert "detail" in res3.json()

    # Malformed JSON
    res4 = client.post(
        "/chat",
        content="not a json",
        headers={"Content-Type": "application/json"}
    )
    assert res4.status_code == 422
    assert "detail" in res4.json()

def test_failover_single_key(client):
    session = "s-failover-single"
    headers = {"X-Simulate-Failure": "key_1=429"}
    res = client.post(
        "/chat",
        json={"session_id": session, "message": "Hello from failover test"},
        headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    # Key 1 failed, key 2 answered
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

def test_failover_status_500(client):
    session = "s-failover-500"
    headers = {"X-Simulate-Failure": "key_1=500"}
    res = client.post(
        "/chat",
        json={"session_id": session, "message": "Testing 500 fallback"},
        headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1

def test_all_keys_failed_returns_503_and_not_in_history(client):
    session = "s-failover-all"
    headers = {"X-Simulate-Failure": "*=429"}
    res = client.post(
        "/chat",
        json={"session_id": session, "message": "Should fail completely"},
        headers=headers
    )
    assert res.status_code == 503
    assert res.json() == {"detail": "all providers unavailable"}

    # Must NOT be added to history
    hist_res = client.get(f"/sessions/{session}/messages")
    assert hist_res.status_code == 404
