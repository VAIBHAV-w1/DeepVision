/**
 * DeepVision Assistant - Website-Only User Guide
 * Handles floating chat widget, query submission, quick prompt chips, and message rendering.
 */

document.addEventListener('DOMContentLoaded', () => {
  const launcher = document.getElementById('btn-chatbot-launcher');
  const panel = document.getElementById('chatbot-panel');
  const closeBtn = document.getElementById('btn-chatbot-close');
  const form = document.getElementById('chatbot-form');
  const input = document.getElementById('chatbot-input');
  const messagesContainer = document.getElementById('chatbot-messages');
  const chipsContainer = document.getElementById('chatbot-chips');

  if (!launcher || !panel || !form || !input || !messagesContainer) {
    return;
  }

  let isOpen = false;
  let isSending = false;

  function toggleChatbot(open) {
    isOpen = (typeof open === 'boolean') ? open : !isOpen;
    if (isOpen) {
      panel.style.display = 'flex';
      launcher.classList.add('active');
      setTimeout(() => input.focus(), 150);
      scrollToBottom();
    } else {
      panel.style.display = 'none';
      launcher.classList.remove('active');
    }
  }

  launcher.addEventListener('click', () => toggleChatbot());
  if (closeBtn) {
    closeBtn.addEventListener('click', () => toggleChatbot(false));
  }

  // Close on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen) {
      toggleChatbot(false);
    }
  });

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function appendMessage(text, isUser = false) {
    const row = document.createElement('div');
    row.className = `chat-bubble-row ${isUser ? 'user' : 'bot'}`;

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${isUser ? 'user' : 'bot'}`;

    // Format newlines into paragraphs or line breaks safely
    const formatted = text.replace(/\n/g, '<br>');
    bubble.innerHTML = formatted;

    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
  }

  function showTypingIndicator() {
    const row = document.createElement('div');
    row.className = 'chat-bubble-row bot typing-indicator-row';
    row.id = 'chatbot-typing';

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble bot typing-indicator';
    bubble.innerHTML = '<span></span><span></span><span></span>';

    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const typing = document.getElementById('chatbot-typing');
    if (typing) {
      typing.remove();
    }
  }

  async function submitQuery(queryText) {
    const cleanText = queryText ? queryText.trim() : '';
    if (!cleanText || isSending) return;

    isSending = true;
    input.value = '';
    appendMessage(cleanText, true);

    // Hide chips after first user query to keep chat clean
    if (chipsContainer) {
      chipsContainer.style.display = 'none';
    }

    showTypingIndicator();

    try {
      const csrfToken = window.getCsrfToken ? window.getCsrfToken() : '';
      const response = await fetch('/api/assistant/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ message: cleanText })
      });

      removeTypingIndicator();

      if (response.ok) {
        const data = await response.json();
        if (data && data.reply) {
          appendMessage(data.reply, false);
        } else {
          appendMessage("I\'m here to assist with DeepVision features. Could you rephrase your question?", false);
        }
      } else {
        appendMessage("I can only help with questions about using DeepVision and its features.", false);
      }
    } catch (err) {
      removeTypingIndicator();
      appendMessage("Unable to reach assistant service right now. Please try again shortly.", false);
    } finally {
      isSending = false;
      input.focus();
    }
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    submitQuery(input.value);
  });

  // Handle suggested chip clicks
  if (chipsContainer) {
    chipsContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.chatbot-chip');
      if (btn && btn.dataset.query) {
        submitQuery(btn.dataset.query);
      }
    });
  }
});