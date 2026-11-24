import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.config import DATABASE_URL

def get_db_path() -> str:
    url = DATABASE_URL
    if url.startswith("sqlite:////"):
        path = "/" + url[len("sqlite:////"):]
    elif url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
    elif url.startswith("sqlite://"):
        path = url[len("sqlite://"):]
    else:
        path = url
    return path

def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    parent_dir = os.path.dirname(path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id);
            """)
    finally:
        conn.close()

def check_db_healthy() -> bool:
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return cursor.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return False

def session_exists(session_id: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()

def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            item: Dict[str, Any] = {
                "role": row["role"],
                "content": row["content"]
            }
            if row["role"] == "assistant" and row["metadata"]:
                try:
                    item["metadata"] = json.loads(row["metadata"])
                except Exception:
                    item["metadata"] = {}
            result.append(item)
        return result
    finally:
        conn.close()

def add_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    conn = get_connection()
    try:
        with conn:
            meta_json = json.dumps(metadata) if metadata is not None else None
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, meta_json, now_iso)
            )
    finally:
        conn.close()
