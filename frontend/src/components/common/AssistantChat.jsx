import React, { useState, useRef, useEffect } from 'react';
import { api } from '../../services/api';

export function AssistantChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      sender: 'bot',
      text: 'Hello! I am your DeepVision Assistant. I can guide you on setting up cameras, using Original or Tracking + Detection modes, configuring alerts, and reviewing video evidence. What would you like help with?',
    },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  const handleSend = async (e) => {
    e?.preventDefault();
    const query = input.trim();
    if (!query || sending) return;

    setMessages((prev) => [...prev, { sender: 'user', text: query }]);
    setInput('');
    setSending(true);

    try {
      const res = await api.assistant.chat(query);
      if (res && res.reply) {
        setMessages((prev) => [...prev, { sender: 'bot', text: res.reply }]);
      } else {
        setMessages((prev) => [
          ...prev,
          { sender: 'bot', text: 'Sorry, I could not process your query at this time.' },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { sender: 'bot', text: 'Error connecting to DeepVision Assistant.' },
      ]);
    } finally {
      setSending(false);
    }
  };

  const handleQuickTopic = (topic) => {
    setInput(topic);
  };

  return (
    <div id="deepvision-chatbot-wrapper" className="chatbot-wrapper">
      {/* Floating Launcher Button */}
      <button
        type="button"
        id="btn-chatbot-launcher"
        className="chatbot-launcher-btn"
        aria-label="Open DeepVision Assistant"
        title="Ask DeepVision Assistant"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="chatbot-launcher-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M 21 15 a 2 2 0 0 1 -2 2 H 7 l -4 4 V 5 a 2 2 0 0 1 2 -2 h 14 a 2 2 0 0 1 2 2 z"></path>
          </svg>
        </div>
        <span className="chatbot-launcher-text">DeepVision Assistant</span>
        <span className="chatbot-launcher-dot"></span>
      </button>

      {/* Compact Assistant Modal Panel */}
      {isOpen && (
        <div
          id="chatbot-panel"
          className="chatbot-panel"
          role="dialog"
          aria-modal="true"
          aria-label="DeepVision Assistant Chat"
          style={{ display: 'flex' }}
        >
          {/* Panel Header */}
          <div className="chatbot-header">
            <div className="chatbot-header-info">
              <div className="chatbot-avatar-emblem">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M 23 7 l -7 5 7 5 V 7 z"></path>
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                </svg>
              </div>
              <div>
                <div className="chatbot-title">DeepVision Assistant</div>
                <div className="chatbot-subtitle">Website &amp; AI Guide &bull; Active</div>
              </div>
            </div>
            <button
              type="button"
              id="btn-chatbot-close"
              className="btn-chatbot-close"
              aria-label="Close Assistant"
              onClick={() => setIsOpen(false)}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>

          {/* Chat Messages Stream */}
          <div id="chatbot-messages" className="chatbot-messages">
            {messages.map((m, idx) => (
              <div key={idx} className={`chat-bubble-row ${m.sender}`}>
                <div className={`chat-bubble ${m.sender}`}>
                  <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{m.text}</p>
                </div>
              </div>
            ))}
            {sending && (
              <div className="chat-bubble-row bot">
                <div className="chat-bubble bot">
                  <p style={{ margin: 0, fontStyle: 'italic', opacity: 0.8 }}>Thinking...</p>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />

            {/* Suggested Quick Prompt Chips */}
            <div className="chatbot-chips-wrap" id="chatbot-chips">
              <span className="chatbot-chip-label">Quick topics:</span>
              <button
                type="button"
                className="chatbot-chip"
                onClick={() => handleQuickTopic('How do I add a camera?')}
              >
                How do I add a camera?
              </button>
              <button
                type="button"
                className="chatbot-chip"
                onClick={() => handleQuickTopic('What is Tracking mode?')}
              >
                What is Tracking mode?
              </button>
              <button
                type="button"
                className="chatbot-chip"
                onClick={() => handleQuickTopic('How does Smart Tracking work?')}
              >
                How does Smart Tracking work?
              </button>
              <button
                type="button"
                className="chatbot-chip"
                onClick={() => handleQuickTopic('How do alerts work?')}
              >
                How do alerts work?
              </button>
              <button
                type="button"
                className="chatbot-chip"
                onClick={() => handleQuickTopic('Why is my camera offline?')}
              >
                Why is my camera offline?
              </button>
            </div>
          </div>

          {/* Chatbot Input Footer */}
          <form id="chatbot-form" className="chatbot-input-bar" onSubmit={handleSend}>
            <input
              type="text"
              id="chatbot-input"
              className="chatbot-input"
              placeholder="Ask about cameras, detection, tracking..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending}
              autoComplete="off"
              aria-label="Chat message input"
            />
            <button
              type="submit"
              id="btn-chatbot-send"
              className="btn-chatbot-send"
              disabled={sending || !input.trim()}
              aria-label="Send message"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default AssistantChat;
