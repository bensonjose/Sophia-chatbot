const chatArea = document.getElementById('chatArea');
const messagesEl = document.getElementById('messages');
const emptyState = document.getElementById('emptyState');
const form = document.getElementById('composerForm');
const input = document.getElementById('promptInput');
const sendBtn = document.getElementById('sendBtn');
const chatListEl = document.getElementById('chatList');
const newChatBtn = document.getElementById('newChatBtn');
const toggleSidebarBtn = document.getElementById('toggleSidebar');
const sidebar = document.getElementById('sidebar');

const STORAGE_KEY = 'groq_chat_conversations';
let conversations = loadConversations();
let activeId = null;
let isStreaming = false;

function loadConversations() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}
function saveConversations() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
}

function newConversation() {
  const convo = { id: crypto.randomUUID(), title: 'New chat', messages: [] };
  conversations.unshift(convo);
  activeId = convo.id;
  saveConversations();
  renderSidebar();
  renderMessages();
}

function getActive() {
  return conversations.find(c => c.id === activeId);
}

function renderSidebar() {
  chatListEl.innerHTML = '';
  conversations.forEach(c => {
    const item = document.createElement('div');
    item.className = 'chat-item' + (c.id === activeId ? ' active' : '');
    item.textContent = c.title;
    item.addEventListener('click', () => {
      activeId = c.id;
      renderSidebar();
      renderMessages();
    });
    chatListEl.appendChild(item);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Minimal markdown-ish rendering: fenced code blocks + inline code
function renderContent(text) {
  const escaped = escapeHtml(text);
  const withBlocks = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => {
    return `<pre><code>${code}</code></pre>`;
  });
  const withInline = withBlocks.replace(/`([^`]+)`/g, '<code>$1</code>');
  return withInline;
}

function renderMessages() {
  const convo = getActive();
  messagesEl.innerHTML = '';
  if (!convo || convo.messages.length === 0) {
    emptyState.style.display = 'flex';
    return;
  }
  emptyState.style.display = 'none';
  convo.messages.forEach(msg => {
    messagesEl.appendChild(buildMessageEl(msg.role, msg.content));
  });
  chatArea.scrollTop = chatArea.scrollHeight;
}

function buildMessageEl(role, content) {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role}`;
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? 'U' : 'S';
  const body = document.createElement('div');
  body.className = 'msg-body';
  const nameLabel = document.createElement('div');
  nameLabel.className = 'msg-name';
  nameLabel.textContent = role === 'user' ? 'You' : 'Sophia';
  const contentEl = document.createElement('div');
  contentEl.className = 'msg-content';
  contentEl.innerHTML = renderContent(content);
  body.appendChild(nameLabel);
  body.appendChild(contentEl);
  wrap.appendChild(avatar);
  wrap.appendChild(body);
  return wrap;
}

function autoResize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 180) + 'px';
}
input.addEventListener('input', () => {
  autoResize();
  sendBtn.disabled = input.value.trim().length === 0 || isStreaming;
});
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll('.suggestion-card').forEach(card => {
  card.addEventListener('click', () => {
    input.value = card.dataset.prompt;
    autoResize();
    sendBtn.disabled = false;
    form.requestSubmit();
  });
});

newChatBtn.addEventListener('click', newConversation);
toggleSidebarBtn.addEventListener('click', () => sidebar.classList.toggle('collapsed'));

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || isStreaming) return;

  if (!activeId) newConversation();
  const convo = getActive();

  if (convo.messages.length === 0) {
    convo.title = text.slice(0, 40) + (text.length > 40 ? '…' : '');
  }
  convo.messages.push({ role: 'user', content: text });
  saveConversations();
  renderSidebar();
  renderMessages();

  input.value = '';
  autoResize();
  sendBtn.disabled = true;
  isStreaming = true;

  // Add assistant placeholder with typing indicator
  const assistantWrap = buildMessageEl('assistant', '');
  const contentEl = assistantWrap.querySelector('.msg-content');
  contentEl.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  messagesEl.appendChild(assistantWrap);
  chatArea.scrollTop = chatArea.scrollHeight;

  let fullText = '';
  let firstChunk = true;

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: convo.messages }),
    });

    if (!resp.ok || !resp.body) {
      throw new Error('Request failed: ' + resp.status);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const dataStr = line.slice(6);
        if (dataStr === '[DONE]') continue;
        try {
          const parsed = JSON.parse(dataStr);
          if (parsed.error) {
            fullText += `\n\n**Error:** ${parsed.error}`;
            contentEl.innerHTML = `<span class="error-text">${escapeHtml(fullText)}</span>`;
            continue;
          }
          if (parsed.content) {
            if (firstChunk) {
              contentEl.innerHTML = '';
              firstChunk = false;
            }
            fullText += parsed.content;
            contentEl.innerHTML = renderContent(fullText);
            chatArea.scrollTop = chatArea.scrollHeight;
          }
        } catch {}
      }
    }
  } catch (err) {
    contentEl.innerHTML = `<span class="error-text">Something went wrong: ${escapeHtml(err.message)}</span>`;
  }

  convo.messages.push({ role: 'assistant', content: fullText || '(no response)' });
  saveConversations();
  isStreaming = false;
  sendBtn.disabled = input.value.trim().length === 0;
});

// Init
if (conversations.length > 0) {
  activeId = conversations[0].id;
}
renderSidebar();
renderMessages();
