/*
===================================================================
  VoxCore — app.js

  Handles:
    - Background canvas
    - Pipeline SSE
    - Video information
    - AI video summary
    - RAG chat UI
===================================================================
*/

'use strict';


// ============================================================
// STATE
// ============================================================

let currentJobId = null;

let chatEnabled = false;

let isSending = false;

let currentEventSource = null;


// ============================================================
// ANIMATED BACKGROUND
// ============================================================

(function initCanvas() {

  const canvas =
    document.getElementById(
      'bg-canvas'
    );

  if (!canvas) {
    return;
  }

  const ctx =
    canvas.getContext('2d');

  let W;
  let H;
  let particles;


  const PARTICLE_COUNT = 80;


  function resize() {

    W =
      canvas.width =
      window.innerWidth;

    H =
      canvas.height =
      window.innerHeight;

  }


  function randomParticle() {

    return {

      x:
        Math.random() * W,

      y:
        Math.random() * H,

      r:
        Math.random() * 1.6 + 0.3,

      vx:
        (Math.random() - 0.5) * 0.25,

      vy:
        (Math.random() - 0.5) * 0.25,

      alpha:
        Math.random() * 0.5 + 0.15,

      hue:
        Math.random() < 0.5
          ? 263
          : 192,

    };

  }


  function init() {

    resize();

    particles =
      Array.from(
        {
          length:
            PARTICLE_COUNT
        },
        randomParticle
      );

  }


  function draw() {

    ctx.clearRect(
      0,
      0,
      W,
      H
    );


    // Radial gradient

    const grd =
      ctx.createRadialGradient(
        W * 0.35,
        H * 0.35,
        0,
        W * 0.5,
        H * 0.5,
        Math.max(W, H) * 0.75
      );


    grd.addColorStop(
      0,
      'rgba(124,58,237,0.06)'
    );

    grd.addColorStop(
      0.5,
      'rgba(6,182,212,0.03)'
    );

    grd.addColorStop(
      1,
      'rgba(0,0,0,0)'
    );


    ctx.fillStyle =
      grd;

    ctx.fillRect(
      0,
      0,
      W,
      H
    );


    // Particles

    particles.forEach(
      p => {

        p.x += p.vx;

        p.y += p.vy;


        if (p.x < 0) {
          p.x = W;
        }

        if (p.x > W) {
          p.x = 0;
        }

        if (p.y < 0) {
          p.y = H;
        }

        if (p.y > H) {
          p.y = 0;
        }


        ctx.beginPath();

        ctx.arc(
          p.x,
          p.y,
          p.r,
          0,
          Math.PI * 2
        );


        ctx.fillStyle =
          `hsla(
            ${p.hue},
            80%,
            70%,
            ${p.alpha}
          )`;

        ctx.fill();

      }
    );


    // Connections

    for (
      let i = 0;
      i < particles.length;
      i++
    ) {

      for (
        let j = i + 1;
        j < particles.length;
        j++
      ) {

        const dx =
          particles[i].x -
          particles[j].x;

        const dy =
          particles[i].y -
          particles[j].y;

        const dist =
          Math.sqrt(
            dx * dx +
            dy * dy
          );


        if (dist < 110) {

          ctx.beginPath();

          ctx.moveTo(
            particles[i].x,
            particles[i].y
          );

          ctx.lineTo(
            particles[j].x,
            particles[j].y
          );


          ctx.strokeStyle =
            `rgba(
              124,
              58,
              237,
              ${0.08 * (1 - dist / 110)}
            )`;

          ctx.lineWidth = 0.6;

          ctx.stroke();

        }

      }

    }


    requestAnimationFrame(
      draw
    );

  }


  window.addEventListener(
    'resize',
    resize
  );


  init();

  draw();

})();


// ============================================================
// START PIPELINE
// ============================================================

function startPipeline() {

  const urlInput =
    document.getElementById(
      'yt-url'
    );


  if (!urlInput) {
    return;
  }


  const url =
    urlInput.value.trim();


  // Validation

  if (!url) {

    showToast(
      'Please paste a YouTube URL first.'
    );

    urlInput.focus();

    return;

  }


  if (
    !url.includes(
      'youtube.com'
    )
    &&
    !url.includes(
      'youtu.be'
    )
  ) {

    showToast(
      "That doesn't look like a YouTube URL. Please check and try again."
    );

    return;

  }


  // Reset UI

  resetPipeline();

  setProcessingState(
    true
  );


  // Start backend

  fetch(
    '/process',
    {
      method: 'POST',

      headers: {
        'Content-Type':
          'application/json'
      },

      body: JSON.stringify({
        url: url
      })

    }
  )

    .then(
      response => {

        return response.json();

      }
    )

    .then(
      data => {

        if (data.error) {

          showToast(
            data.error
          );

          setProcessingState(
            false
          );

          return;

        }


        currentJobId =
          data.job_id;


        openSSEStream(
          data.job_id
        );

      }
    )

    .catch(
      error => {

        showToast(
          'Server error: ' +
          error.message
        );

        setProcessingState(
          false
        );

      }
    );

}


// ============================================================
// SSE STREAM
// ============================================================

function openSSEStream(
  jobId
) {

  const progressCard =
    document.getElementById(
      'progress-card'
    );


  if (progressCard) {

    progressCard.style.display =
      'block';

  }


  if (currentEventSource) {

    currentEventSource.close();

  }


  const evtSource =
    new EventSource(
      `/stream/${jobId}`
    );


  currentEventSource =
    evtSource;


  // ----------------------------------------------------------
  // STEP
  // ----------------------------------------------------------

  evtSource.addEventListener(
    'step',
    event => {

      try {

        const data =
          JSON.parse(
            event.data
          );


        updateStep(
          data.step,
          data.status,
          data.message
        );

      }
      catch (error) {

        console.error(
          'Invalid step event:',
          error
        );

      }

    }
  );


  // ----------------------------------------------------------
  // DONE
  // ----------------------------------------------------------

  evtSource.addEventListener(
    'done',
    event => {

      try {

        const data =
          JSON.parse(
            event.data
          );


        evtSource.close();

        currentEventSource =
          null;


        setProcessingState(
          false
        );


        // Video information

        showVideoInfo(
          data
        );


        // Transcript

        // The transcript preview is
        // already part of the video card.


        // AI SUMMARY

        if (data.summary) {

          showSummary(
            data.summary
          );

        }


        // Chat

        enableChat(
          data.title
        );

      }
      catch (error) {

        console.error(
          'Invalid done event:',
          error
        );

        showToast(
          'Unable to display processing result.'
        );

      }

    }
  );


  // ----------------------------------------------------------
  // BACKEND ERROR
  // ----------------------------------------------------------

  evtSource.addEventListener(
    'error',
    event => {

      try {

        const data =
          JSON.parse(
            event.data
          );


        showToast(
          'Pipeline error: ' +
          data.message
        );

      }
      catch (_) {

        showToast(
          'An unexpected error occurred during processing.'
        );

      }


      evtSource.close();

      currentEventSource =
        null;

      setProcessingState(
        false
      );

    }
  );


  // ----------------------------------------------------------
  // CONNECTION ERROR
  // ----------------------------------------------------------

  evtSource.onerror =
    () => {

      /*
        Do not immediately show an error here.
        Flask closes the SSE stream after sending
        the "done" event.
      */

      if (
        evtSource.readyState ===
        EventSource.CLOSED
      ) {

        return;

      }

    };

}


// ============================================================
// UPDATE PIPELINE STEP
// ============================================================

function updateStep(
  step,
  status,
  message
) {

  const item =
    document.getElementById(
      `step-${step}`
    );


  const msgEl =
    document.getElementById(
      `msg-${step}`
    );


  const badgeEl =
    document.getElementById(
      `badge-${step}`
    );


  if (!item) {
    return;
  }


  // Remove previous states

  item.classList.remove(
    'running',
    'done',
    'error'
  );


  // Current state

  if (
    status ===
    'running'
  ) {

    item.classList.add(
      'running'
    );

  }
  else if (
    status ===
    'done'
  ) {

    item.classList.add(
      'done'
    );

  }
  else if (
    status ===
    'error'
  ) {

    item.classList.add(
      'error'
    );

  }


  if (msgEl) {

    msgEl.textContent =
      message ||
      '';

  }


  if (badgeEl) {

    if (
      status ===
      'running'
    ) {

      badgeEl.textContent =
        '●';

    }
    else if (
      status ===
      'done'
    ) {

      badgeEl.textContent =
        '✓';

    }
    else if (
      status ===
      'error'
    ) {

      badgeEl.textContent =
        '✕';

    }
    else {

      badgeEl.textContent =
        '';

    }

  }

}


// ============================================================
// VIDEO INFORMATION
// ============================================================

function showVideoInfo(
  data
) {

  const card =
    document.getElementById(
      'video-info-card'
    );


  if (!card) {
    return;
  }


  card.style.display =
    'block';


  // Title

  const title =
    document.getElementById(
      'video-title'
    );


  if (title) {

    title.textContent =
      data.title ||
      'Unknown Title';

  }


  // Transcript

  const transcript =
    document.getElementById(
      'transcript-preview'
    );


  if (transcript) {

    transcript.textContent =
      data.transcript_preview
        ? data.transcript_preview + '…'
        : '';

  }


  // Thumbnail

  const thumb =
    document.getElementById(
      'video-thumb'
    );


  if (thumb) {

    if (data.thumbnail) {

      thumb.src =
        data.thumbnail;

      thumb.style.display =
        'block';

    }
    else {

      thumb.style.display =
        'none';

    }

  }


  // Duration

  const duration =
    parseInt(
      data.duration || 0,
      10
    );


  const durationEl =
    document.getElementById(
      'stat-duration'
    );


  if (durationEl) {

    durationEl.lastChild.textContent =
      ' ' +
      formatDuration(
        duration
      );

  }


  // RAG chunks

  const chunksEl =
    document.getElementById(
      'stat-chunks'
    );


  if (chunksEl) {

    chunksEl.lastChild.textContent =
      ' ' +
      (
        data.chunk_count ||
        0
      ) +
      ' chunks';

  }

}


// ============================================================
// FORMAT DURATION
// ============================================================

function formatDuration(
  secs
) {

  const h =
    Math.floor(
      secs / 3600
    );


  const m =
    Math.floor(
      (secs % 3600) / 60
    );


  const s =
    secs % 60;


  if (h > 0) {

    return (
      `${h}:` +
      `${String(m).padStart(2, '0')}:` +
      `${String(s).padStart(2, '0')}`
    );

  }


  return (
    `${m}:` +
    `${String(s).padStart(2, '0')}`
  );

}


// ============================================================
// AI VIDEO SUMMARY
// ============================================================

function showSummary(
  summary
) {

  const card =
    document.getElementById(
      'summary-card'
    );


  if (
    !card ||
    !summary
  ) {

    return;

  }


  // ----------------------------------------------------------
  // Overview
  // ----------------------------------------------------------

  const overview =
    document.getElementById(
      'summary-overview'
    );


  if (overview) {

    overview.textContent =
      summary.overview ||
      '';

  }


  // ----------------------------------------------------------
  // Key Points
  // ----------------------------------------------------------

  const keyPoints =
    document.getElementById(
      'summary-key-points'
    );


  if (keyPoints) {

    keyPoints.innerHTML =
      '';


    const points =
      Array.isArray(
        summary.key_points
      )
        ? summary.key_points
        : [];


    points.forEach(
      point => {

        const li =
          document.createElement(
            'li'
          );


        li.textContent =
          point;


        keyPoints.appendChild(
          li
        );

      }
    );

  }


  // ----------------------------------------------------------
  // Topics
  // ----------------------------------------------------------

  const topics =
    document.getElementById(
      'summary-topics'
    );


  if (topics) {

    topics.innerHTML =
      '';


    const topicList =
      Array.isArray(
        summary.topics
      )
        ? summary.topics
        : [];


    topicList.forEach(
      topic => {

        const topicCard =
          document.createElement(
            'div'
          );


        topicCard.className =
          'summary-topic';


        // Title

        const title =
          document.createElement(
            'h4'
          );


        title.textContent =
          topic.title ||
          'Topic';


        // Timestamp

        const timestamp =
          document.createElement(
            'span'
          );


        timestamp.className =
          'topic-timestamp';


        timestamp.textContent =
          `${formatVideoTimestamp(topic.start)} → ${formatVideoTimestamp(topic.end)}`;


        // Summary

        const description =
          document.createElement(
            'p'
          );


        description.textContent =
          topic.summary ||
          '';


        topicCard.appendChild(
          title
        );


        topicCard.appendChild(
          timestamp
        );


        topicCard.appendChild(
          description
        );


        topics.appendChild(
          topicCard
        );

      }
    );

  }


  // ----------------------------------------------------------
  // Takeaways
  // ----------------------------------------------------------

  const takeaways =
    document.getElementById(
      'summary-takeaways'
    );


  if (takeaways) {

    takeaways.innerHTML =
      '';


    const takeawayList =
      Array.isArray(
        summary.takeaways
      )
        ? summary.takeaways
        : [];


    takeawayList.forEach(
      takeaway => {

        const li =
          document.createElement(
            'li'
          );


        li.textContent =
          takeaway;


        takeaways.appendChild(
          li
        );

      }
    );

  }


  // ----------------------------------------------------------
  // Show summary card
  // ----------------------------------------------------------

  card.style.display =
    'block';

}


// ============================================================
// VIDEO TIMESTAMP
// ============================================================

function formatVideoTimestamp(
  seconds
) {

  seconds =
    Number(seconds) || 0;


  const hours =
    Math.floor(
      seconds / 3600
    );


  const minutes =
    Math.floor(
      (seconds % 3600) / 60
    );


  const secs =
    Math.floor(
      seconds % 60
    );


  if (hours > 0) {

    return (
      `${hours}:` +
      `${String(minutes).padStart(2, '0')}:` +
      `${String(secs).padStart(2, '0')}`
    );

  }


  return (
    `${String(minutes).padStart(2, '0')}:` +
    `${String(secs).padStart(2, '0')}`
  );

}


// ============================================================
// ENABLE CHAT
// ============================================================

function enableChat(
  title
) {

  chatEnabled =
    true;


  const input =
    document.getElementById(
      'chat-input'
    );


  const sendBtn =
    document.getElementById(
      'send-btn'
    );


  const subtitle =
    document.getElementById(
      'chat-subtitle'
    );


  const statusDot =
    document.getElementById(
      'chat-status-dot'
    );


  const chips =
    document.querySelectorAll(
      '.example-chip'
    );


  if (input) {

    input.disabled =
      false;

  }


  if (sendBtn) {

    sendBtn.disabled =
      false;

  }


  if (subtitle) {

    subtitle.textContent =
      title
        ? title.substring(
            0,
            60
          ) +
          (
            title.length > 60
              ? '…'
              : ''
          )
        : 'Ready';

  }


  if (statusDot) {

    statusDot.classList.add(
      'active'
    );

  }


  chips.forEach(
    chip => {

      chip.disabled =
        false;

    }
  );


  // Bot greeting

  appendBotMessage(
    `I've finished processing **"${title}"**. Ask me anything about this video — I'll answer based on the transcript.`,
    null
  );

}


// ============================================================
// SEND CHAT MESSAGE
// ============================================================

function sendMessage() {

  if (
    !chatEnabled ||
    isSending
  ) {

    return;

  }


  const input =
    document.getElementById(
      'chat-input'
    );


  if (!input) {
    return;
  }


  const query =
    input.value.trim();


  if (!query) {
    return;
  }


  if (!currentJobId) {

    showToast(
      'No processed video is available.'
    );

    return;

  }


  input.value =
    '';

  autoResize(
    input
  );


  // User message

  appendUserMessage(
    query
  );


  // Typing indicator

  const typingId =
    appendTypingIndicator();


  isSending =
    true;


  const sendBtn =
    document.getElementById(
      'send-btn'
    );


  if (sendBtn) {

    sendBtn.disabled =
      true;

  }


  fetch(
    '/chat',
    {
      method: 'POST',

      headers: {
        'Content-Type':
          'application/json'
      },

      body: JSON.stringify({

        job_id:
          currentJobId,

        query:
          query

      })

    }
  )

    .then(
      response => {

        return response.json();

      }
    )

    .then(
      data => {

        removeTypingIndicator(
          typingId
        );


        if (data.error) {

          showToast(
            data.error
          );

        }
        else {

          appendBotMessage(
            data.answer,
            data.chunks_used
          );

        }

      }
    )

    .catch(
      error => {

        removeTypingIndicator(
          typingId
        );


        showToast(
          'Chat error: ' +
          error.message
        );

      }
    )

    .finally(
      () => {

        isSending =
          false;


        if (sendBtn) {

          sendBtn.disabled =
            false;

        }


        input.focus();

      }
    );

}


// ============================================================
// CHAT ENTER KEY
// ============================================================

function handleChatKey(
  event
) {

  if (
    event.key === 'Enter' &&
    !event.shiftKey
  ) {

    event.preventDefault();

    sendMessage();

  }

}


// ============================================================
// EXAMPLE QUERY
// ============================================================

function fillExample(
  button
) {

  if (!chatEnabled) {
    return;
  }


  const input =
    document.getElementById(
      'chat-input'
    );


  if (!input) {
    return;
  }


  input.value =
    button.textContent;


  autoResize(
    input
  );


  input.focus();

}


// ============================================================
// USER MESSAGE
// ============================================================

function appendUserMessage(
  text
) {

  const area =
    document.getElementById(
      'messages-area'
    );


  if (!area) {
    return;
  }


  hideWelcome();


  const row =
    document.createElement(
      'div'
    );


  row.className =
    'msg-row user';


  row.innerHTML = `
    <div class="bubble-avatar">
      U
    </div>

    <div>
      <div class="bubble">
        ${escapeHtml(text)}
      </div>
    </div>
  `;


  area.appendChild(
    row
  );


  scrollToBottom();

}


// ============================================================
// BOT MESSAGE
// ============================================================

function appendBotMessage(
  text,
  chunksUsed
) {

  const area =
    document.getElementById(
      'messages-area'
    );


  if (!area) {
    return;
  }


  hideWelcome();


  const chunksHtml =
    chunksUsed != null
      ? `<span class="chunks-badge">⚡ ${chunksUsed} context chunks</span>`
      : '';


  const row =
    document.createElement(
      'div'
    );


  row.className =
    'msg-row bot';


  row.innerHTML = `
    <div class="bubble-avatar">

      <svg
        width="16"
        height="16"
        viewBox="0 0 28 28"
        fill="none"
      >

        <circle
          cx="14"
          cy="14"
          r="13"
          stroke="white"
          stroke-width="1.5"
        />

        <path
          d="M8 14 Q11 8 14 14 Q17 20 20 14"
          stroke="white"
          stroke-width="2"
          stroke-linecap="round"
          fill="none"
        />

      </svg>

    </div>


    <div>

      <div class="bubble">
        ${renderMarkdown(text)}
      </div>

      <div class="bubble-meta">
        VoxCore AI ${chunksHtml}
      </div>

    </div>
  `;


  area.appendChild(
    row
  );


  scrollToBottom();

}


// ============================================================
// TYPING INDICATOR
// ============================================================

function appendTypingIndicator() {

  const area =
    document.getElementById(
      'messages-area'
    );


  const id =
    'typing-' +
    Date.now();


  const row =
    document.createElement(
      'div'
    );


  row.id =
    id;


  row.className =
    'msg-row bot';


  row.innerHTML = `
    <div class="bubble-avatar">

      <svg
        width="16"
        height="16"
        viewBox="0 0 28 28"
        fill="none"
      >

        <circle
          cx="14"
          cy="14"
          r="13"
          stroke="white"
          stroke-width="1.5"
        />

        <path
          d="M8 14 Q11 8 14 14 Q17 20 20 14"
          stroke="white"
          stroke-width="2"
          stroke-linecap="round"
          fill="none"
        />

      </svg>

    </div>


    <div
      class="bubble"
      style="
        background:rgba(124,58,237,0.08);
        border:1px solid rgba(124,58,237,0.2)
      "
    >

      <div class="typing-indicator">

        <div class="typing-dot"></div>

        <div class="typing-dot"></div>

        <div class="typing-dot"></div>

      </div>

    </div>
  `;


  area.appendChild(
    row
  );


  scrollToBottom();


  return id;

}


// ============================================================
// REMOVE TYPING
// ============================================================

function removeTypingIndicator(
  id
) {

  const element =
    document.getElementById(
      id
    );


  if (element) {

    element.remove();

  }

}


// ============================================================
// HIDE WELCOME
// ============================================================

function hideWelcome() {

  const welcome =
    document.getElementById(
      'welcome-msg'
    );


  if (welcome) {

    welcome.style.display =
      'none';

  }

}


// ============================================================
// SCROLL CHAT
// ============================================================

function scrollToBottom() {

  const area =
    document.getElementById(
      'messages-area'
    );


  if (area) {

    area.scrollTop =
      area.scrollHeight;

  }

}


// ============================================================
// PROCESSING STATE
// ============================================================

function setProcessingState(
  running
) {

  const btn =
    document.getElementById(
      'process-btn'
    );


  const input =
    document.getElementById(
      'yt-url'
    );


  if (!btn) {
    return;
  }


  const btnText =
    btn.querySelector(
      '.btn-text'
    );


  const btnIcon =
    btn.querySelector(
      '.btn-icon'
    );


  const spinner =
    btn.querySelector(
      '.btn-spinner'
    );


  btn.disabled =
    running;


  if (input) {

    input.disabled =
      running;

  }


  if (btnText) {

    btnText.textContent =
      running
        ? 'Processing'
        : 'Process';

  }


  if (btnIcon) {

    btnIcon.style.display =
      running
        ? 'none'
        : 'flex';

  }


  if (spinner) {

    spinner.style.display =
      running
        ? 'flex'
        : 'none';

  }

}


// ============================================================
// RESET PIPELINE
// ============================================================

function resetPipeline() {

  // ----------------------------------------------------------
  // Close previous SSE connection
  // ----------------------------------------------------------

  if (currentEventSource) {

    currentEventSource.close();

    currentEventSource =
      null;

  }


  // ----------------------------------------------------------
  // Hide cards
  // ----------------------------------------------------------

  const progressCard =
    document.getElementById(
      'progress-card'
    );


  const videoCard =
    document.getElementById(
      'video-info-card'
    );


  const summaryCard =
    document.getElementById(
      'summary-card'
    );


  if (progressCard) {

    progressCard.style.display =
      'none';

  }


  if (videoCard) {

    videoCard.style.display =
      'none';

  }


  if (summaryCard) {

    summaryCard.style.display =
      'none';

  }


  // ----------------------------------------------------------
  // Reset all 7 steps
  // ----------------------------------------------------------

  for (
    let i = 1;
    i <= 7;
    i++
  ) {

    const item =
      document.getElementById(
        `step-${i}`
      );


    const msg =
      document.getElementById(
        `msg-${i}`
      );


    const badge =
      document.getElementById(
        `badge-${i}`
      );


    if (item) {

      item.classList.remove(
        'running',
        'done',
        'error'
      );

    }


    if (msg) {

      msg.textContent =
        'Waiting...';

    }


    if (badge) {

      badge.textContent =
        '';

    }

  }


  // ----------------------------------------------------------
  // Disable chat
  // ----------------------------------------------------------

  chatEnabled =
    false;


  const chatInput =
    document.getElementById(
      'chat-input'
    );


  const sendBtn =
    document.getElementById(
      'send-btn'
    );


  const subtitle =
    document.getElementById(
      'chat-subtitle'
    );


  const statusDot =
    document.getElementById(
      'chat-status-dot'
    );


  if (chatInput) {

    chatInput.disabled =
      true;

    chatInput.value =
      '';

  }


  if (sendBtn) {

    sendBtn.disabled =
      true;

  }


  if (subtitle) {

    subtitle.textContent =
      'Process a video to begin';

  }


  if (statusDot) {

    statusDot.classList.remove(
      'active'
    );

  }


  // ----------------------------------------------------------
  // Clear messages
  // ----------------------------------------------------------

  const area =
    document.getElementById(
      'messages-area'
    );


  if (area) {

    area.innerHTML = `
      <div
        class="welcome-msg"
        id="welcome-msg"
      >

        <div class="welcome-icon">

          <svg
            width="40"
            height="40"
            viewBox="0 0 28 28"
            fill="none"
          >

            <circle
              cx="14"
              cy="14"
              r="13"
              stroke="url(#wlg2)"
              stroke-width="1.5"
            />

            <path
              d="M8 14 Q11 8 14 14 Q17 20 20 14"
              stroke="url(#wlg2)"
              stroke-width="2"
              stroke-linecap="round"
              fill="none"
            />

            <defs>

              <linearGradient
                id="wlg2"
                x1="0"
                y1="0"
                x2="28"
                y2="28"
                gradientUnits="userSpaceOnUse"
              >

                <stop
                  offset="0%"
                  stop-color="#7c3aed"
                />

                <stop
                  offset="100%"
                  stop-color="#06b6d4"
                />

              </linearGradient>

            </defs>

          </svg>

        </div>


        <p class="welcome-title">
          Chat with your video
        </p>


        <p class="welcome-body">
          Paste a YouTube URL on the left and click
          <strong>Process</strong>.
          Once indexed, ask any question about the video content.
        </p>


        <div class="example-queries">

          <p class="examples-label">
            Example questions
          </p>

        </div>

      </div>
    `;

  }


  // ----------------------------------------------------------
  // Reset job
  // ----------------------------------------------------------

  currentJobId =
    null;


  isSending =
    false;

}


// ============================================================
// AUTO RESIZE CHAT
// ============================================================

function autoResize(
  element
) {

  if (!element) {
    return;
  }


  element.style.height =
    'auto';


  element.style.height =
    Math.min(
      element.scrollHeight,
      140
    ) +
    'px';

}


// ============================================================
// ESCAPE HTML
// ============================================================

function escapeHtml(
  text
) {

  return String(text)

    .replace(
      /&/g,
      '&amp;'
    )

    .replace(
      /</g,
      '&lt;'
    )

    .replace(
      />/g,
      '&gt;'
    )

    .replace(
      /"/g,
      '&quot;'
    )

    .replace(
      /'/g,
      '&#039;'
    );

}


// ============================================================
// MARKDOWN
// ============================================================

function renderMarkdown(
  text
) {

  return escapeHtml(
    text
  )

    .replace(
      /\*\*(.*?)\*\*/g,
      '<strong>$1</strong>'
    )

    .replace(
      /\*(.*?)\*/g,
      '<em>$1</em>'
    )

    .replace(
      /^(\d+)\.\s/gm,
      '<br><strong>$1.</strong> '
    )

    .replace(
      /\n/g,
      '<br>'
    );

}


// ============================================================
// TOAST
// ============================================================

function showToast(
  msg
) {

  const toast =
    document.getElementById(
      'toast'
    );


  if (!toast) {
    return;
  }


  toast.textContent =
    msg;


  toast.classList.add(
    'show'
  );


  setTimeout(
    () => {

      toast.classList.remove(
        'show'
      );

    },
    4200
  );

}


// ============================================================
// ENTER KEY FOR URL
// ============================================================

const urlInput =
  document.getElementById(
    'yt-url'
  );


if (urlInput) {

  urlInput.addEventListener(
    'keydown',
    event => {

      if (
        event.key ===
        'Enter'
      ) {

        startPipeline();

      }

    }
  );

}