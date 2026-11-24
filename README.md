# Lyftr AI — Full-Stack LLM Chatbot with Key Failover & Response Caching

A resilient, production-ready Full-Stack LLM Chatbot built with **React**, **FastAPI**, **SQLite**, and **LiteLLM**. Demonstrates multi-turn conversational context, automatic key failover across multiple API keys, and sub-millisecond response caching.

---

## 1. Live URLs

- **Live Frontend**: [https://lyftr-llm-chatbot-qwtwy2rf6-reachbox-scheduler.vercel.app/](https://lyftr-llm-chatbot-qwtwy2rf6-reachbox-scheduler.vercel.app/)
- **Live Backend API**: [https://lyftr-llm-backend.onrender.com](https://lyftr-llm-backend.onrender.com) *(or your deployed Render / Fly.io / Railway URL)*
- **Health Check Endpoint**: [https://lyftr-llm-backend.onrender.com/health](https://lyftr-llm-backend.onrender.com/health)
- **Public GitHub Repository**: [https://github.com/MeetGrover/lyftr-llm-chatbot](https://github.com/MeetGrover/lyftr-llm-chatbot)
- **2–3 Minute Demo Video**: [Demo Video Link](https://loom.com/your-video-link)

---

## 2. Run locally: with Docker and without

### A. Running with Docker & Make (Recommended)

Prerequisites: Docker & Docker Compose installed.

1. **Clone repository and configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env and supply your LLM_API_KEYS (e.g., Google Gemini or Groq API keys)
   ```

2. **Start the whole stack with Make**:
   ```bash
   make up
   ```
   - **Frontend UI**: [http://localhost:3000](http://localhost:3000)
   - **Backend API**: [http://localhost:8000](http://localhost:8000)
   - **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
   - Data is persisted across restarts inside the Docker named volume `lyftr_sqlite_data` mounted at `/data/app.db`.

3. **Stop the stack**:
   ```bash
   make down
   ```

---

### B. Running Locally without Docker

#### Prerequisites:
- Python 3.10+
- Node.js 18+

#### 1. Start the Backend:
```bash
cd backend
python -m venv venv

# On macOS/Linux:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate

pip install -r requirements.txt
cp ../.env.example .env

# Run FastAPI server on port 8000:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Start the Frontend:
```bash
cd frontend
npm install
npm run dev
# Vite will serve at http://localhost:3000 (or http://localhost:5173 depending on port configuration)
```

#### 3. Run Backend Test Suite:
```bash
cd backend
pytest tests -v
```

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Key Fallback Architecture
- **Key Pool Order**: Configured via `LLM_API_KEYS` as a comma-separated list. Keys are assigned sequential identifiers: `key_1`, `key_2`, etc.
- **Failover Logic**: When a request is processed, `key_1` is attempted first. If the key encounters an HTTP 429 (rate limit), quota exhaustion, or 5xx server error, the backend increments `fallback_attempts` and seamlessly falls back to `key_2`.
- **Security & Contract**: The client response reports only the identifier of the answering key (`key_id: "key_1"` or `"key_2"`), never exposing the actual API key. On cache hits, `key_id` is strictly `null` and `fallback_attempts` is `0`.
- **Exhaustion Handling**: If all configured keys fail, the request returns a clean HTTP 503 `{"detail": "all providers unavailable"}` without throwing stack traces or HTML error pages. Failed requests are never saved to session history.

### Response Caching Strategy
- **Exact Cache Key**: The cache key is deterministically generated from `(model, messages)` where `messages` contains the complete sequence `[system_prompt, ...prior_history, new_message]`.
- **Behavior**:
  - The first time a message is sent in a new session, it is executed via `LIVE_INFERENCE` and stored in LiteLLM's local memory cache.
  - Sending the identical message as the first prompt in another session matches the cache key and immediately yields `LLM_CACHE` with stored tokens and near-zero latency.
  - Subsequent multi-turn messages produce different full message sequences, avoiding false cache hits.
- **Test Hook Isolation**: When `X-Simulate-Failure` is passed (with `ENABLE_FAILURE_SIMULATION=true`), the cache is bypassed so key fallback can be tested directly without returning stale cache hits.

### SQLite Session Storage
- **File-Backed Persistence**: In Docker, SQLite stores the database at `/data/app.db` on a Docker named volume (`sqlite_data`), surviving container restarts without external dependencies (no Redis or PostgreSQL).
- **History Isolation**: History is scoped strictly by `session_id`. `GET /sessions/{session_id}/messages` returns stored messages chronologically (oldest first) excluding system prompts.
- **Fail-Safe Integrity**: If an inference fails (HTTP 422 or 503), neither user message nor assistant message is saved to the database.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### 1. Verify Normal Live Inference & Caching
1. Open the UI at [http://localhost:3000](http://localhost:3000).
2. Enter `"What is the capital of France?"` and click Send:
   - Notice badge: `LIVE_INFERENCE`
   - Notice latency (e.g. `400-800 ms`), token counts, and answering key (e.g. `key_1`).
3. Click **"New Session"** in the top navigation.
4. Enter the exact same message: `"What is the capital of France?"` and click Send:
   - Notice badge: `LLM_CACHE`
   - Notice latency is sub-10ms (significantly faster than live call).
   - `key_id` is `null` and `fallback_attempts` is `0`.
   - Token usage matches the original request.

### 2. Verify Key Failover via UI or cURL
The UI features a built-in **"Failover Simulation"** dropdown in the top control bar.

- **Simulate key_1 Failure**:
  Select `key_1=429 (Fallback to key_2)` in the dropdown and send a prompt:
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=429" \
    -d '{"session_id": "s-demo-failover", "message": "Tell me a joke"}'
  ```
  **Response**: HTTP 200, `"key_id": "key_2"`, `"fallback_attempts": 1`.

- **Simulate Total Provider Outage**:
  Select `*=429 (All keys fail -> 503)` in the dropdown:
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: *=429" \
    -d '{"session_id": "s-demo-failover", "message": "Tell me a joke"}'
  ```
  **Response**: HTTP 503 `{"detail": "all providers unavailable"}`.
  Verify nothing was added to history:
  ```bash
  curl http://localhost:8000/sessions/s-demo-failover/messages
  # Returns 404 {"detail": "session not found"}
  ```

### 3. Verify Per-Message Token Usage
- Each assistant bubble displays request-isolated `input_tokens` and `output_tokens`.
- Two equal-length first messages in two separate sessions report consistent input tokens rather than an accumulating counter.

---

## 5. Setup Used: your editor and AI tools

- **Editor / IDE**: VS Code & Antigravity IDE on Windows.
- **AI Coding Assistant**: Google DeepMind Antigravity Pair Programmer.
- **Language & Runtimes**: Python 3.12 (FastAPI, Uvicorn, LiteLLM, Pytest) & Node.js 20+ (Vite, React 19).
- **Containerization**: Multi-stage Docker & Docker Compose.

---

## 6. Bonus features (if any): what you added beyond the requirements and why

1. **Interactive In-UI Failover Simulation Bar**:
   - Added a dropdown in the UI allowing the reviewer or user to trigger `key_1=429`, `key_1=500`, and `*=429` failure simulations with a single click, eliminating the need to execute manual cURL commands during video demonstrations.
2. **Real-Time Gateway & Key Health Indicator**:
   - A live status chip in the navbar that queries `GET /health` to display live server connectivity, number of active keys loaded, and cache readiness.
3. **Session Switcher & On-Demand Reset**:
   - A one-click "New Session" button that generates a fresh session identifier on demand, making it effortless to test cold vs. cached requests side by side.
4. **Developer Mock Inference Mode (`MOCK_LLM=true`)**:
   - Enabled deterministic mock responses if placeholder API keys are used, allowing automated test suites and reviewers to test all failover and caching mechanics locally without requiring paid API credits.
