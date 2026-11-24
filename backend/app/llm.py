import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import litellm
from litellm.caching.caching import Cache
from app.config import (
    KEY_POOL,
    DEFAULT_MODEL,
    ENABLE_FAILURE_SIMULATION,
    MOCK_LLM
)

logger = logging.getLogger(__name__)

# Initialize LiteLLM Cache with in-memory local cache
litellm_cache = Cache(type="local")
litellm.cache = litellm_cache
litellm.enable_cache()

class AllProvidersUnavailableError(Exception):
    """Raised when every key in the key pool fails."""
    pass

def parse_simulation_header(header_val: Optional[str]) -> Dict[str, int]:
    """
    Parses comma-separated <key_id>=<status> pairs, e.g.
    'key_1=429' or 'key_1=429,key_2=500' or '*=429'.
    Allowed statuses: 429, 500, 502, 503.
    """
    if not header_val or not ENABLE_FAILURE_SIMULATION:
        return {}
    res: Dict[str, int] = {}
    parts = [p.strip() for p in header_val.split(",") if p.strip()]
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            try:
                status_code = int(v)
                if status_code in (429, 500, 502, 503):
                    res[k] = status_code
            except ValueError:
                pass
    return res

def get_cache_key(model: str, messages: List[Dict[str, str]]) -> str:
    """Computes cache key for model + full message list."""
    return litellm_cache.get_cache_key(model=model, messages=messages)

def get_from_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    """Retrieves cached response from LiteLLM cache if available."""
    try:
        data = litellm_cache.cache.get_cache(cache_key)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"Error reading from cache: {e}")
    return None

def set_in_cache(cache_key: str, data: Dict[str, Any]) -> None:
    """Stores response in LiteLLM cache."""
    try:
        litellm_cache.cache.set_cache(cache_key, data)
    except Exception as e:
        logger.warning(f"Error writing to cache: {e}")

def _generate_mock_reply(messages: List[Dict[str, str]]) -> str:
    """Deterministic fallback mock response for testing and offline scenarios."""
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break
    
    clean_msg = last_user_msg.lower()
    if "capital of france" in clean_msg:
        return "The capital of France is Paris."
    elif "population" in clean_msg:
        return "The population of Paris is approximately 2.1 million within the city proper."
    elif "joke" in clean_msg:
        return "Why do programmers prefer dark mode? Because light attracts bugs!"
    elif "hello" in clean_msg or "hi" in clean_msg:
        return "Hello! How can I assist you today?"
    else:
        return f"I received your message: '{last_user_msg}'. How else can I assist you?"

def execute_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    simulate_failure_header: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes a chat completion with key failover and response caching.
    
    Returns dict with:
        reply: str
        resolution_source: "LIVE_INFERENCE" or "LLM_CACHE"
        model: str
        latency_ms: int
        input_tokens: int
        output_tokens: int
        key_id: Optional[str] (None on LLM_CACHE)
        fallback_attempts: int (0 on LLM_CACHE)
    """
    target_model = model or DEFAULT_MODEL
    start_time = time.perf_counter()
    simulation_map = parse_simulation_header(simulate_failure_header)
    
    cache_key = get_cache_key(target_model, messages)
    
    # Caching check:
    # If failure simulation header is present and enabled, bypass cache to ensure keys failover is tested
    if not simulation_map:
        cached_entry = get_from_cache(cache_key)
        if cached_entry:
            latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            return {
                "reply": cached_entry["reply"],
                "resolution_source": "LLM_CACHE",
                "model": cached_entry.get("model", target_model),
                "latency_ms": latency_ms,
                "input_tokens": cached_entry["input_tokens"],
                "output_tokens": cached_entry["output_tokens"],
                "key_id": None,
                "fallback_attempts": 0
            }

    # Live Inference with Key Fallback
    fallback_attempts = 0
    success_result: Optional[Dict[str, Any]] = None
    answering_key_id: Optional[str] = None

    for key_id, api_key in KEY_POOL:
        # Check simulated failure
        sim_code = simulation_map.get("*") or simulation_map.get(key_id)
        if sim_code:
            logger.info(f"Simulating failure {sim_code} on {key_id}")
            fallback_attempts += 1
            continue

        # Check if real execution or mock fallback is needed
        is_placeholder = (
            api_key.startswith("key_") and 
            ("placeholder" in api_key or "fallback" in api_key)
        )
        
        if MOCK_LLM or is_placeholder:
            # Deterministic mock inference
            reply = _generate_mock_reply(messages)
            try:
                input_tokens = litellm.token_counter(model="gpt-3.5-turbo", messages=messages)
                output_tokens = litellm.token_counter(model="gpt-3.5-turbo", text=reply)
            except Exception:
                input_tokens = sum(len(m.get("content", "").split()) for m in messages) * 2
                output_tokens = len(reply.split()) * 2

            answering_key_id = key_id
            success_result = {
                "reply": reply,
                "input_tokens": max(1, input_tokens),
                "output_tokens": max(1, output_tokens),
                "model": target_model
            }
            break

        try:
            # Actual LiteLLM call
            response = litellm.completion(
                model=target_model,
                messages=messages,
                api_key=api_key,
                timeout=15.0
            )
            reply = response.choices[0].message.content or ""
            
            # Extract or count tokens
            usage = getattr(response, "usage", None)
            if usage and hasattr(usage, "prompt_tokens") and usage.prompt_tokens:
                input_tokens = usage.prompt_tokens
            else:
                input_tokens = litellm.token_counter(model=target_model, messages=messages)
                
            if usage and hasattr(usage, "completion_tokens") and usage.completion_tokens:
                output_tokens = usage.completion_tokens
            else:
                output_tokens = litellm.token_counter(model=target_model, text=reply)

            answering_key_id = key_id
            success_result = {
                "reply": reply,
                "input_tokens": max(1, input_tokens),
                "output_tokens": max(1, output_tokens),
                "model": getattr(response, "model", target_model) or target_model
            }
            break

        except Exception as e:
            logger.warning(f"Key {key_id} failed with error: {e}")
            fallback_attempts += 1
            continue

    if success_result is None:
        raise AllProvidersUnavailableError("all providers unavailable")

    latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    
    # Store in cache
    set_in_cache(cache_key, success_result)

    return {
        "reply": success_result["reply"],
        "resolution_source": "LIVE_INFERENCE",
        "model": success_result["model"],
        "latency_ms": latency_ms,
        "input_tokens": success_result["input_tokens"],
        "output_tokens": success_result["output_tokens"],
        "key_id": answering_key_id,
        "fallback_attempts": fallback_attempts
    }
