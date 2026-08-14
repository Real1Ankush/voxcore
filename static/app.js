/* ===================================================================
   VoxCore — app.js
   Handles: background canvas, pipeline SSE, chat UI
   =================================================================== */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let currentJobId = null;
let chatEnabled  = false;
let isSending    = false;

// ── Animated background (particle field) ─────────────────────────────────────
(function initCanvas() {
  const canvas = document.getElementById('bg-canvas');
  const ctx    = canvas.getContext('2d');
  let W, H, particles;

  const PARTICLE_COUNT = 80;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function randomParticle() {
    return {
      x:    Math.random() * W,
      y:    Math.random() * H,
      r:    Math.random() * 1.6 + 0.3,
      vx:   (Math.random() - 0.5) * 0.25,
      vy:   (Math.random() - 0.5) * 0.25,
      alpha: Math.random() * 0.5 + 0.15,
      hue:  Math.random() < 0.5 ? 263 : 192,   // violet or cyan
    };
  }

  function init() {
    resize();
    particles = Array.from({ length: PARTICLE_COUNT }, randomParticle);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // subtle radial gradient overlay
    const grd = ctx.createRadialGradient(W * 0.35, H * 0.35, 0, W * 0.5, H * 0.5, Math.max(W, H) * 0.75);
    grd.addColorStop(0,   'rgba(124,58,237,0.06)');
    grd.addColorStop(0.5, 'rgba(6,182,212,0.03)');
    grd.addColorStop(1,   'rgba(0,0,0,0)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, W, H);

    // particles
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = W;
      if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H;
      if (p.y > H) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 80%, 70%, ${p.alpha})`;
      ctx.fill();
    });

    // draw connections
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx   = particles[i].x - particles[j].x;
        const dy   = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 110) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(124,58,237,${0.08 * (1 - dist / 110)})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  init();
  draw();
})();


// ── Pipeline: start ───────────────────────────────────────────────────────────
function startPipeline() {
  const urlInput  = document.getElementById('yt-url');
  const url       = urlInput.value.trim();

  if (!url) {
    showToast('Please paste a YouTube URL first.');
    urlInput.focus();
    return;
  }

  if (!url.includes('youtube.com') && !url.includes('youtu.be')) {
    showToast('That doesn\'t look like a YouTube URL. Please check and try again.');
    return;
  }

  // Reset UI
  resetPipeline();
  setProcessingState(true);

  fetch('/process', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ url }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) { showToast(data.error); setProcessingState(false); return; }
      currentJobId = data.job_id;
      openSSEStream(data.job_id);
    })
    .catch(err => {
      showToast('Server error: ' + err.message);
      setProcessingState(false);
    });
}

// ── SSE stream ────────────────────────────────────────────────────────────────
function openSSEStream(jobId) {
  const progressCard = document.getElementById('progress-card');
  progressCard.style.display = 'block';

  const evtSource = new EventSource(`/stream/${jobId}`);

  evtSource.addEventListener('step', e => {
    const d = JSON.parse(e.data);
    updateStep(d.step, d.status, d.message);
  });

  evtSource.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    evtSource.close();
    setProcessingState(false);
    showVideoInfo(d);
    enableChat(d.title);
  });

  evtSource.addEventListener('error', e => {
    try {
      const d = JSON.parse(e.data);
      showToast('Pipeline error: ' + d.message);
    } catch (_) {
      showToast('An unexpected error occurred during processing.');
    }
    evtSource.close();
    setProcessingState(false);
  });

  evtSource.onerror = () => {
    evtSource.close();
    setProcessingState(false);
  };
}

// ── Step UI update ────────────────────────────────────────────────────────────
function updateStep(step, status, message) {
  const item  = document.getElementById(`step-${step}`);
  const msgEl = document.getElementById(`msg-${step}`);
  if (!item || !msgEl) return;

  item.classList.remove('running', 'done', 'error');
  item.classList.add(status === 'done' ? 'done' : status === 'running' ? 'running' : '');
  msgEl.textContent = message;
}

// ── Video info reveal ─────────────────────────────────────────────────────────
function showVideoInfo(data) {
  const card = document.getElementById('video-info-card');
  card.style.display = 'block';

  document.getElementById('video-title').textContent     = data.title || 'Unknown Title';
  document.getElementById('transcript-preview').textContent = (data.transcript_preview || '') + '…';

  const thumb = document.getElementById('video-thumb');
  if (data.thumbnail) {
    thumb.src = data.thumbnail;
    thumb.style.display = 'block';
  } else {
    thumb.style.display = 'none';
  }

  // Duration
  const dur      = parseInt(data.duration || 0, 10);
  const durEl    = document.getElementById('stat-duration');
  durEl.lastChild.textContent = ' ' + formatDuration(dur);

  // Chunks
  const chunksEl = document.getElementById('stat-chunks');
  chunksEl.lastChild.textContent = ' ' + (data.chunk_count || 0) + ' chunks';
}

function formatDuration(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

// ── Enable chat ───────────────────────────────────────────────────────────────
function enableChat(title) {
  chatEnabled = true;

  const input      = document.getElementById('chat-input');
  const sendBtn    = document.getElementById('send-btn');
  const subtitle   = document.getElementById('chat-subtitle');
  const statusDot  = document.getElementById('chat-status-dot');
  const chips      = document.querySelectorAll('.example-chip');

  input.disabled   = false;
  sendBtn.disabled = false;
  subtitle.textContent = title ? title.substring(0, 60) + (title.length > 60 ? '…' : '') : 'Ready';
  statusDot.classList.add('active');
  chips.forEach(c => c.disabled = false);

  // Bot greeting
  appendBotMessage(
    `I've finished processing **"${title}"**. Ask me anything about this video — I'll answer based on the transcript.`,
    null
  );
}

// ── Chat ──────────────────────────────────────────────────────────────────────
function sendMessage() {
  if (!chatEnabled || isSending) return;

  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;

  input.value = '';
  autoResize(input);

  appendUserMessage(query);
  const typingId = appendTypingIndicator();

  isSending = true;
  document.getElementById('send-btn').disabled = true;

  fetch('/chat', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ job_id: currentJobId, query }),
  })
    .then(r => r.json())
    .then(data => {
      removeTypingIndicator(typingId);
      if (data.error) {
        showToast(data.error);
      } else {
        appendBotMessage(data.answer, data.chunks_used);
      }
    })
    .catch(err => {
      removeTypingIndicator(typingId);
      showToast('Chat error: ' + err.message);
    })
    .finally(() => {
      isSending = false;
      document.getElementById('send-btn').disabled = false;
      document.getElementById('chat-input').focus();
    });
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function fillExample(btn) {
  if (!chatEnabled) return;
  const input = document.getElementById('chat-input');
  input.value = btn.textContent;
  autoResize(input);
  input.focus();
}

// ── Message builders ──────────────────────────────────────────────────────────
function appendUserMessage(text) {
  const area = document.getElementById('messages-area');
  hideWelcome();

  const row = document.createElement('div');
  row.className = 'msg-row user';
  row.innerHTML = `
    <div class="bubble-avatar">U</div>
    <div>
      <div class="bubble">${escapeHtml(text)}</div>
    </div>
  `;
  area.appendChild(row);
  scrollToBottom();
}

function appendBotMessage(text, chunksUsed) {
  const area = document.getElementById('messages-area');
  hideWelcome();

  const chunksHtml = chunksUsed != null
    ? `<span class="chunks-badge">⚡ ${chunksUsed} context chunks</span>`
    : '';

  const row = document.createElement('div');
  row.className = 'msg-row bot';
  row.innerHTML = `
    <div class="bubble-avatar">
      <svg width="16" height="16" viewBox="0 0 28 28" fill="none">
        <circle cx="14" cy="14" r="13" stroke="white" stroke-width="1.5"/>
        <path d="M8 14 Q11 8 14 14 Q17 20 20 14" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
      </svg>
    </div>
    <div>
      <div class="bubble">${renderMarkdown(text)}</div>
      <div class="bubble-meta">VoxCore AI ${chunksHtml}</div>
    </div>
  `;
  area.appendChild(row);
  scrollToBottom();
}

function appendTypingIndicator() {
  const area = document.getElementById('messages-area');
  const id   = 'typing-' + Date.now();
  const row  = document.createElement('div');
  row.id         = id;
  row.className  = 'msg-row bot';
  row.innerHTML  = `
    <div class="bubble-avatar">
      <svg width="16" height="16" viewBox="0 0 28 28" fill="none">
        <circle cx="14" cy="14" r="13" stroke="white" stroke-width="1.5"/>
        <path d="M8 14 Q11 8 14 14 Q17 20 20 14" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>
      </svg>
    </div>
    <div class="bubble" style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2)">
      <div class="typing-indicator">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>
  `;
  area.appendChild(row);
  scrollToBottom();
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function hideWelcome() {
  const w = document.getElementById('welcome-msg');
  if (w) w.style.display = 'none';
}

function scrollToBottom() {
  const area = document.getElementById('messages-area');
  area.scrollTop = area.scrollHeight;
}

function setProcessingState(running) {
  const btn     = document.getElementById('process-btn');
  const btnText = btn.querySelector('.btn-text');
  const btnIcon = btn.querySelector('.btn-icon');
  const spinner = btn.querySelector('.btn-spinner');
  const input   = document.getElementById('yt-url');

  btn.disabled    = running;
  input.disabled  = running;
  btnText.textContent = running ? 'Processing' : 'Process';
  btnIcon.style.display  = running ? 'none' : 'flex';
  spinner.style.display  = running ? 'flex' : 'none';
}

function resetPipeline() {
  // Hide cards
  document.getElementById('progress-card').style.display   = 'none';
  document.getElementById('video-info-card').style.display = 'none';

  // Reset all steps
  for (let i = 1; i <= 6; i++) {
    const item = document.getElementById(`step-${i}`);
    const msg  = document.getElementById(`msg-${i}`);
    if (item) item.classList.remove('running', 'done');
    if (msg)  msg.textContent = 'Waiting...';
  }

  // Disable chat
  chatEnabled = false;
  document.getElementById('chat-input').disabled   = true;
  document.getElementById('send-btn').disabled     = true;
  document.getElementById('chat-subtitle').textContent = 'Process a video to begin';
  document.getElementById('chat-status-dot').classList.remove('active');

  // Clear messages
  const area = document.getElementById('messages-area');
  area.innerHTML = '';
  const welcome = document.createElement('div');
  welcome.id = 'welcome-msg';
  welcome.className = 'welcome-msg';
  welcome.innerHTML = `
    <div class="welcome-icon">
      <svg width="40" height="40" viewBox="0 0 28 28" fill="none">
        <circle cx="14" cy="14" r="13" stroke="url(#wlg2)" stroke-width="1.5"/>
        <path d="M8 14 Q11 8 14 14 Q17 20 20 14" stroke="url(#wlg2)" stroke-width="2" stroke-linecap="round" fill="none"/>
        <defs>
          <linearGradient id="wlg2" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#7c3aed"/>
            <stop offset="100%" stop-color="#06b6d4"/>
          </linearGradient>
        </defs>
      </svg>
    </div>
    <p class="welcome-title">Chat with your video</p>
    <p class="welcome-body">Paste a YouTube URL on the left and click <strong>Process</strong>. Once indexed, ask any question about the video content.</p>
  `;
  area.appendChild(welcome);
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Minimal markdown: bold, newlines, numbered lists
function renderMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g,   '<em>$1</em>')
    .replace(/^(\d+)\.\s/gm, '<br><strong>$1.</strong> ')
    .replace(/\n/g, '<br>');
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 4200);
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.getElementById('yt-url').addEventListener('keydown', e => {
  if (e.key === 'Enter') startPipeline();
});
