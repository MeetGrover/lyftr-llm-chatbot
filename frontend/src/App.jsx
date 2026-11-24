import React, { useState, useEffect, useRef } from "react";
import {
  Send,
  RotateCcw,
  Cpu,
  Zap,
  Layers,
  AlertTriangle,
  Server,
  Settings,
  HelpCircle,
  Database
} from "lucide-react";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function generateSessionId() {
  return "s-" + Math.random().toString(36).substring(2, 10);
}

export default function App() {
  // A new session starts on each page load
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);

  // Backend Health state
  const [health, setHealth] = useState({ status: "checking", keys: 0, cache: false });

  // Failover test hook control (for reviewer demonstration)
  const [simulateFailure, setSimulateFailure] = useState("none");
  const [customFailure, setCustomFailure] = useState("");
  const [showConfig, setShowConfig] = useState(false);

  const messagesEndRef = useRef(null);

  // Check backend health on mount
  useEffect(() => {
    fetchHealth();
  }, []);

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        const data = await res.json();
        setHealth({
          status: "connected",
          keys: data.keys_configured,
          cache: data.cache_enabled
        });
      } else {
        setHealth({ status: "error", keys: 0, cache: false });
      }
    } catch {
      setHealth({ status: "disconnected", keys: 0, cache: false });
    }
  };

  const startNewSession = () => {
    setSessionId(generateSessionId());
    setMessages([]);
    setErrorBanner(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleSendMessage = async () => {
    const trimmed = inputMessage.trim();
    if (!trimmed || isLoading) return;

    // Reset input immediately per spec: empty after sending
    setInputMessage("");
    setErrorBanner(null);

    // Append user message to UI
    const userMsg = { role: "user", content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    // Construct headers
    const headers = {
      "Content-Type": "application/json"
    };

    let failHeader = null;
    if (simulateFailure === "key_1_429") failHeader = "key_1=429";
    else if (simulateFailure === "key_1_500") failHeader = "key_1=500";
    else if (simulateFailure === "all_429") failHeader = "*=429";
    else if (simulateFailure === "custom" && customFailure.trim()) {
      failHeader = customFailure.trim();
    }

    if (failHeader) {
      headers["X-Simulate-Failure"] = failHeader;
    }

    const payload = {
      session_id: sessionId,
      message: trimmed
    };

    if (systemPrompt.trim()) {
      payload.system_prompt = systemPrompt.trim();
    }

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (!res.ok) {
        // Readable error in the chat
        const errorDetail =
          typeof data.detail === "string"
            ? data.detail
            : Array.isArray(data.detail)
            ? data.detail.map((e) => e.msg || JSON.stringify(e)).join(", ")
            : JSON.stringify(data.detail);

        const errorMsg = `Error ${res.status}: ${errorDetail}`;
        setMessages((prev) => [
          ...prev,
          { role: "error", content: errorMsg }
        ]);
        setErrorBanner(errorMsg);
      } else {
        // Success: assistant message with metadata
        const assistantMsg = {
          role: "assistant",
          content: data.reply,
          metadata: data.metadata
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }
    } catch (err) {
      const netErrorMsg = `Network Error: Could not connect to backend at ${API_BASE}. ${err.message}`;
      setMessages((prev) => [
        ...prev,
        { role: "error", content: netErrorMsg }
      ]);
      setErrorBanner(netErrorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">L</div>
          <div>
            <div className="brand-title">
              Lyftr AI Chatbot
              <span className="brand-badge">Failover & Cache Gateway</span>
            </div>
          </div>
        </div>

        <div className="header-actions">
          <div className="status-indicator" title="Backend connection status">
            <span
              className={`status-dot ${
                health.status === "connected" ? "" : "error"
              }`}
            />
            <span>
              {health.status === "connected"
                ? `Online (${health.keys} Keys, Cache Active)`
                : health.status === "checking"
                ? "Checking Backend..."
                : "Backend Offline"}
            </span>
          </div>

          <button
            className="btn-secondary"
            onClick={() => setShowConfig(!showConfig)}
            title="Toggle Settings & Failure Simulation"
          >
            <Settings size={14} />
            {showConfig ? "Hide Controls" : "Controls & Failover"}
          </button>

          <button
            className="btn-secondary"
            onClick={startNewSession}
            title="Start a new chat session"
          >
            <RotateCcw size={14} />
            New Session
          </button>
        </div>
      </header>

      {/* Control bar: Session info & System prompt */}
      <div className="controls-bar">
        <div className="controls-row">
          <div className="session-info">
            <Database size={14} />
            <span>Active Session:</span>
            <span className="session-id-tag">{sessionId}</span>
          </div>

          {/* Failover test hook selector */}
          <div className="simulation-control">
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              X-Simulate-Failure:
            </span>
            <select
              className="select-input"
              value={simulateFailure}
              onChange={(e) => setSimulateFailure(e.target.value)}
              title="Select failover test hook simulation header"
            >
              <option value="none">None (Standard)</option>
              <option value="key_1_429">key_1=429 (Fallback to key_2)</option>
              <option value="key_1_500">key_1=500 (Fallback to key_2)</option>
              <option value="all_429">*=429 (All keys fail -&gt; 503)</option>
              <option value="custom">Custom Header...</option>
            </select>

            {simulateFailure === "custom" && (
              <input
                type="text"
                className="select-input"
                placeholder="e.g. key_1=429,key_2=500"
                value={customFailure}
                onChange={(e) => setCustomFailure(e.target.value)}
                style={{ width: "160px" }}
              />
            )}
          </div>
        </div>

        {/* Optional System prompt input */}
        <div className="system-prompt-wrapper">
          <label className="system-prompt-label" htmlFor="system-prompt">
            System Prompt (Optional)
          </label>
          <input
            id="system-prompt"
            data-testid="system-prompt-input"
            className="system-prompt-input"
            type="text"
            placeholder="e.g. You are a concise expert software engineer."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </div>
      </div>

      {/* Messages Scroll Area */}
      <main className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-chat">
            <HelpCircle className="empty-chat-icon" />
            <h3>No messages yet</h3>
            <p>
              Ask any question to test multi-turn state, response caching, and key
              failover.
            </p>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Tip: Asking the same first question in a new session demonstrates{" "}
              <strong style={{ color: "#c084fc" }}>LLM_CACHE</strong>.
            </p>
          </div>
        )}

        {messages.map((msg, index) => {
          if (msg.role === "user") {
            return (
              <div key={index} className="chat-message-row user">
                <div className="user-bubble">{msg.content}</div>
              </div>
            );
          }

          if (msg.role === "error") {
            return (
              <div key={index} className="chat-message-row error">
                <div className="error-message-bubble">
                  <AlertTriangle size={18} />
                  <span>{msg.content}</span>
                </div>
              </div>
            );
          }

          // Assistant message container adhering strictly to frontend contract
          return (
            <div
              key={index}
              className="chat-message-row assistant"
              data-testid="assistant-message"
            >
              <div className="assistant-bubble-container">
                <div className="assistant-text">{msg.content}</div>

                {msg.metadata && (
                  <div className="metadata-container">
                    {/* Resolution source: exactly LIVE_INFERENCE or LLM_CACHE */}
                    <span
                      data-testid="meta-source"
                      className={`meta-badge ${
                        msg.metadata.resolution_source === "LIVE_INFERENCE"
                          ? "badge-source-live"
                          : "badge-source-cache"
                      }`}
                    >
                      {msg.metadata.resolution_source === "LIVE_INFERENCE" ? (
                        <Zap size={12} />
                      ) : (
                        <Layers size={12} />
                      )}
                      {msg.metadata.resolution_source}
                    </span>

                    {/* Model used */}
                    <span data-testid="meta-model" className="meta-badge badge-model">
                      <Cpu size={12} />
                      {msg.metadata.model}
                    </span>

                    {/* Latency */}
                    <span
                      data-testid="meta-latency"
                      className="meta-badge badge-latency"
                    >
                      {msg.metadata.latency_ms} ms
                    </span>

                    {/* Input Tokens */}
                    <span
                      data-testid="meta-input-tokens"
                      className="meta-badge badge-tokens"
                    >
                      In: {msg.metadata.input_tokens}
                    </span>

                    {/* Output Tokens */}
                    <span
                      data-testid="meta-output-tokens"
                      className="meta-badge badge-tokens"
                    >
                      Out: {msg.metadata.output_tokens}
                    </span>

                    {/* Key Id & Fallback info (helpful for demo & verification) */}
                    {msg.metadata.key_id && (
                      <span className="meta-badge badge-key" title="Active Key ID">
                        <Server size={12} />
                        {msg.metadata.key_id}
                        {msg.metadata.fallback_attempts > 0 &&
                          ` (${msg.metadata.fallback_attempts} fallback)`}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="chat-message-row assistant">
            <div
              className="assistant-bubble-container"
              style={{ color: "var(--text-muted)", fontStyle: "italic" }}
            >
              Generating response...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* Input bar */}
      <footer className="chat-input-container">
        <div className="input-box-wrapper">
          <textarea
            data-testid="chat-input"
            className="chat-textarea"
            rows={1}
            placeholder="Type your message here... (Enter to send, Shift+Enter for newline)"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <button
            data-testid="send-button"
            className="send-button"
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || isLoading}
            title="Send Message"
          >
            <Send size={16} />
          </button>
        </div>
        <div className="input-footer">
          <span>Multi-turn session history stored in SQLite</span>
          <span>LiteLLM Key Fallback & Caching Gateway</span>
        </div>
      </footer>
    </div>
  );
}
