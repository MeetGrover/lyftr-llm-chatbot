import os
from typing import List, Tuple
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
ALLOWED_ORIGINS: List[str] = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,*").split(",")
    if origin.strip()
]
ENABLE_FAILURE_SIMULATION: bool = os.getenv("ENABLE_FAILURE_SIMULATION", "true").lower() in ("true", "1", "yes")
DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini/gemini-2.0-flash")
MOCK_LLM: bool = os.getenv("MOCK_LLM", "false").lower() in ("true", "1", "yes")

raw_keys = [k.strip() for k in os.getenv("LLM_API_KEYS", "key_1_placeholder,key_2_placeholder").split(",") if k.strip()]
if len(raw_keys) < 2:
    # Ensure minimum 2 keys are in the pool if missing
    raw_keys.extend([f"key_{i}_fallback" for i in range(len(raw_keys) + 1, 3)])

KEY_POOL: List[Tuple[str, str]] = [
    (f"key_{idx + 1}", key_val)
    for idx, key_val in enumerate(raw_keys)
]

def get_keys_configured() -> int:
    return len(KEY_POOL)
