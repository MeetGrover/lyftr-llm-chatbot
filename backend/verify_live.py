import sys
import time
import requests

def test_api(base_url: str):
    base_url = base_url.rstrip("/")
    print(f"\n=======================================================")
    print(f" Testing Lyftr AI Chatbot Gateway at: {base_url}")
    print(f"=======================================================\n")

    # 1. Test /health
    print("[1/6] Testing GET /health ...", end=" ")
    try:
        r = requests.get(f"{base_url}/health", timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data}"
        assert data.get("keys_configured") >= 2, f"Expected >= 2 keys, got {data.get('keys_configured')}"
        assert data.get("cache_enabled") is True, f"Expected cache_enabled True, got {data.get('cache_enabled')}"
        print(f"PASSED (Keys: {data['keys_configured']}, Cache: {data['cache_enabled']})")
    except Exception as e:
        print(f"FAILED: {e}")
        return

    # 2. Test Live Inference (First Message)
    session_1 = f"test-sess-{int(time.time())}"
    print(f"[2/6] Testing POST /chat (Live Inference on session '{session_1}') ...", end=" ")
    try:
        payload = {"session_id": session_1, "message": "What is the capital of France?"}
        r = requests.post(f"{base_url}/chat", json=payload, timeout=25)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data1 = r.json()
        meta1 = data1["metadata"]
        assert meta1["resolution_source"] == "LIVE_INFERENCE", f"Expected LIVE_INFERENCE, got {meta1['resolution_source']}"
        assert meta1["key_id"] == "key_1", f"Expected key_1, got {meta1['key_id']}"
        assert meta1["fallback_attempts"] == 0
        assert meta1["input_tokens"] > 0 and meta1["output_tokens"] > 0
        print(f"PASSED (Reply: '{data1['reply'][:30]}...', Latency: {meta1['latency_ms']}ms, Key: {meta1['key_id']})")
    except Exception as e:
        print(f"FAILED: {e}")
        return

    # 3. Test Response Caching (Same first message in NEW session)
    session_2 = f"test-sess-cached-{int(time.time())}"
    print(f"[3/6] Testing Response Caching (Identical message in session '{session_2}') ...", end=" ")
    try:
        payload2 = {"session_id": session_2, "message": "What is the capital of France?"}
        r = requests.post(f"{base_url}/chat", json=payload2, timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data2 = r.json()
        meta2 = data2["metadata"]
        assert meta2["resolution_source"] == "LLM_CACHE", f"Expected LLM_CACHE, got {meta2['resolution_source']}"
        assert meta2["key_id"] is None, f"Expected null key_id on cache, got {meta2['key_id']}"
        assert meta2["fallback_attempts"] == 0, f"Expected 0 fallback attempts, got {meta2['fallback_attempts']}"
        assert data2["reply"] == data1["reply"], "Cached reply does not match original"
        print(f"PASSED (Source: LLM_CACHE, Latency: {meta2['latency_ms']}ms, key_id: null)")
    except Exception as e:
        print(f"FAILED: {e}")

    # 4. Test Multi-Turn History
    print(f"[4/6] Testing Multi-turn Context & GET /sessions/{session_1}/messages ...", end=" ")
    try:
        # Send second message
        r = requests.post(f"{base_url}/chat", json={"session_id": session_1, "message": "What is its population?"}, timeout=25)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        
        # Query history
        r_hist = requests.get(f"{base_url}/sessions/{session_1}/messages", timeout=15)
        assert r_hist.status_code == 200, f"Expected 200, got {r_hist.status_code}: {r_hist.text}"
        hist_data = r_hist.json()
        msgs = hist_data.get("messages", [])
        assert len(msgs) == 4, f"Expected 4 messages (2 user, 2 assistant), got {len(msgs)}"
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        print(f"PASSED (Found {len(msgs)} messages stored chronologically in SQLite)")
    except Exception as e:
        print(f"FAILED: {e}")

    # 5. Test Key Failover Hook (key_1=429 -> fallback to key_2)
    session_failover = f"test-sess-failover-{int(time.time())}"
    print(f"[5/6] Testing Failover Hook (X-Simulate-Failure: key_1=429) ...", end=" ")
    try:
        headers = {"X-Simulate-Failure": "key_1=429"}
        payload = {"session_id": session_failover, "message": "Tell me a short fun fact"}
        r = requests.post(f"{base_url}/chat", json=payload, headers=headers, timeout=25)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data_fo = r.json()
        meta_fo = data_fo["metadata"]
        assert meta_fo["key_id"] == "key_2", f"Expected key_2, got {meta_fo['key_id']}"
        assert meta_fo["fallback_attempts"] == 1, f"Expected 1 fallback attempt, got {meta_fo['fallback_attempts']}"
        print(f"PASSED (key_1 failed -> key_2 succeeded, fallback_attempts: 1)")
    except Exception as e:
        print(f"FAILED: {e}")

    # 6. Test Total Failure (*=429 -> 503, nothing added to history)
    session_outage = f"test-sess-outage-{int(time.time())}"
    print(f"[6/6] Testing Total Failure Hook (X-Simulate-Failure: *=429 -> 503) ...", end=" ")
    try:
        headers = {"X-Simulate-Failure": "*=429"}
        payload = {"session_id": session_outage, "message": "Should fail with 503"}
        r = requests.post(f"{base_url}/chat", json=payload, headers=headers, timeout=25)
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
        assert r.json().get("detail") == "all providers unavailable", f"Unexpected error detail: {r.text}"
        
        # Verify not in history
        r_hist = requests.get(f"{base_url}/sessions/{session_outage}/messages", timeout=15)
        assert r_hist.status_code == 404, f"Expected 404 for failed session, got {r_hist.status_code}"
        print(f"PASSED (Clean 503 'all providers unavailable', verified session not added to DB)")
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=======================================================")
    print(" ALL TESTS COMPLETE!")
    print("=======================================================\n")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    test_api(target)
