from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    ALLOWED_ORIGINS,
    get_keys_configured,
    DEFAULT_MODEL
)
from app.database import (
    init_db,
    check_db_healthy,
    session_exists,
    get_session_messages,
    add_message
)
from app.models import (
    HealthResponse,
    ChatRequest,
    ChatResponse,
    ChatResponseMetadata,
    SessionMessagesResponse,
    SessionMessage
)
from app.llm import execute_chat, AllProvidersUnavailableError

DEFAULT_SYSTEM_PROMPT = "You are a helpful, accurate, and concise AI assistant."

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    init_db()
    yield

app = FastAPI(
    title="LLM Chatbot Gateway",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None, # Clean API: only the 3 required endpoints
    redoc_url=None,
    openapi_url=None
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if "*" not in ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.get("/health", response_model=HealthResponse)
def get_health():
    """Returns 200 once the app is running, the database is reachable and the key pool is loaded."""
    if not check_db_healthy():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable"
        )
    return HealthResponse(
        status="ok",
        keys_configured=get_keys_configured(),
        cache_enabled=True
    )

@app.post("/chat", response_model=ChatResponse)
def post_chat(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure")
):
    """
    Main chat completion endpoint with key fallback, response caching,
    and failure simulation support.
    """
    trimmed_msg = req.message.strip()
    session_id = req.session_id.strip()

    # Retrieve prior messages for multi-turn context
    prior_messages = get_session_messages(session_id)
    
    # Construct LLM prompt sequence
    system_prompt = req.system_prompt or DEFAULT_SYSTEM_PROMPT
    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in prior_messages:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
    llm_messages.append({"role": "user", "content": trimmed_msg})

    try:
        chat_result = execute_chat(
            messages=llm_messages,
            model=DEFAULT_MODEL,
            simulate_failure_header=x_simulate_failure
        )
    except AllProvidersUnavailableError:
        # A request that fails (503) is NOT added to session history
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="all providers unavailable"
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="all providers unavailable"
        )

    # Persist user message and assistant reply to SQLite
    add_message(session_id=session_id, role="user", content=trimmed_msg, metadata=None)
    
    assistant_db_metadata = {
        "resolution_source": chat_result["resolution_source"],
        "input_tokens": chat_result["input_tokens"],
        "output_tokens": chat_result["output_tokens"]
    }
    add_message(
        session_id=session_id,
        role="assistant",
        content=chat_result["reply"],
        metadata=assistant_db_metadata
    )

    metadata = ChatResponseMetadata(
        resolution_source=chat_result["resolution_source"],
        model=chat_result["model"],
        latency_ms=chat_result["latency_ms"],
        input_tokens=chat_result["input_tokens"],
        output_tokens=chat_result["output_tokens"],
        key_id=chat_result["key_id"],
        fallback_attempts=chat_result["fallback_attempts"]
    )

    return ChatResponse(
        session_id=session_id,
        reply=chat_result["reply"],
        metadata=metadata
    )

@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
def get_session_history(session_id: str):
    """
    Returns the stored history of one session from SQLite, oldest first,
    without the system prompt.
    """
    if not session_exists(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found"
        )
    messages = get_session_messages(session_id)
    return SessionMessagesResponse(
        session_id=session_id,
        messages=[
            SessionMessage(
                role=m["role"],
                content=m["content"],
                metadata=m.get("metadata")
            )
            for m in messages
        ]
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)

