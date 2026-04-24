'use strict';

let realtimeStarted = false;
let currentMode = 'check-in';

const AUTO_RESET_MS = 7000;

function renderRecords(records) {
  const list = document.getElementById('recent-list');
  if (!list) return;

  if (!records.length) {
    list.innerHTML = '<p class="empty">No records yet today.</p>';
    return;
  }

  list.innerHTML = records
    .slice()
    .reverse()
    .map((record) => `
      <div class="row">
        <div class="avatar">${record.name.charAt(0).toUpperCase()}</div>
        <div class="meta">
          <p class="name">${record.name}</p>
          <p class="time">${record.time}</p>
        </div>
      </div>
    `)
    .join('');
}

function startClock() {
  const dateEl = document.getElementById('live-date');
  const timeEl = document.getElementById('live-time');
  if (!dateEl || !timeEl) return;

  const formatterDate = new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
  const formatterTime = new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const render = () => {
    const now = new Date();
    dateEl.textContent = formatterDate.format(now);
    timeEl.textContent = formatterTime.format(now);
  };

  render();
  setInterval(render, 1000);
}

function pollRecentRecognitions() {
  const countEl = document.getElementById('today-count');

  const refresh = () => {
    fetch('/api/public/recent')
      .then((res) => res.json())
      .then((json) => {
        if (!json.success) return;
        if (countEl) countEl.textContent = String(json.data.today_count);
        renderRecords(json.data.records || []);
      })
      .catch(() => {
        // Ignore temporary network interruptions.
      });
  };

  refresh();
  setInterval(refresh, 5000);
}

function mapStatusState(status) {
  const state = (status.state || '').toLowerCase();

  if (state === 'waiting_for_face') {
    return {
      visualState: 'no-face',
      title: 'No face detected',
      hint: 'Stand in front of the camera',
      bannerClass: 'neutral',
    };
  }

  if (state === 'awaiting_recognition') {
    return {
      visualState: 'align-face',
      title: 'Align face in guide',
      hint: 'Center eyes and face shape',
      bannerClass: 'info',
    };
  }

  if (state === 'awaiting_liveness' || state === 'ready_to_confirm') {
    return {
      visualState: 'liveness',
      title: 'Liveness check in progress',
      hint: 'Blink or turn head slightly',
      bannerClass: 'info',
    };
  }

  if (state === 'stream_started') {
    return {
      visualState: 'align-face',
      title: 'Camera started',
      hint: 'Align face in guide',
      bannerClass: 'info',
    };
  }

  if (state === 'attendance_confirmed') {
    return {
      visualState: 'success',
      title: 'Attendance confirmed',
      hint: 'Ready for next employee soon',
      bannerClass: 'ok',
    };
  }

  if (state === 'liveness_failed') {
    return {
      visualState: 'failed',
      title: 'Liveness failed',
      hint: 'Retry with blink or head movement',
      bannerClass: 'error',
    };
  }

  if (state === 'business_rejected') {
    return {
      visualState: 'failed',
      title: 'Scan not accepted',
      hint: 'Retry or check attendance rules',
      bannerClass: 'warn',
    };
  }

  if (state === 'camera_unavailable' || state === 'camera_read_failed' || state === 'model_not_ready') {
    return {
      visualState: 'failed',
      title: 'Kiosk unavailable',
      hint: 'Please contact an operator',
      bannerClass: 'error',
    };
  }

  return {
    visualState: 'verifying',
    title: 'Verifying face',
    hint: 'Please hold still',
    bannerClass: 'info',
  };
}

function setActiveVisualState(visualState) {
  document.querySelectorAll('.state-row').forEach((row) => {
    if (!(row instanceof HTMLElement)) return;
    row.classList.remove('active', 'success', 'failed');
    if (row.dataset.visualState !== visualState) return;

    if (visualState === 'success') {
      row.classList.add('success');
    } else if (visualState === 'failed') {
      row.classList.add('failed');
    } else {
      row.classList.add('active');
    }
  });
}

function renderKioskStatus(status) {
  const banner = document.getElementById('status-banner');
  const label = document.getElementById('status-state-label');
  const title = document.getElementById('status-state-title');
  const message = document.getElementById('scan-status-message');
  const code = document.getElementById('status-state-code');
  const hint = document.getElementById('status-short-hint');

  if (!banner || !label || !title || !message || !code || !hint) return;

  const mapped = mapStatusState(status);
  const updatedAt = status.updated_at ? new Date(status.updated_at) : null;
  const now = Date.now();
  const shouldAutoReset =
    updatedAt &&
    ['attendance_confirmed', 'liveness_failed', 'business_rejected'].includes(status.state) &&
    now - updatedAt.getTime() > AUTO_RESET_MS;

  const renderedState = shouldAutoReset
    ? {
        visualState: 'align-face',
        title: currentMode === 'check-out' ? 'Ready for next check out' : 'Ready for next check in',
        hint: 'Next employee may step forward',
        bannerClass: 'neutral',
      }
    : mapped;

  banner.classList.remove('neutral', 'info', 'ok', 'warn', 'error');
  banner.classList.add(renderedState.bannerClass);

  label.textContent = currentMode === 'check-out' ? 'Check Out Kiosk' : 'Check In Kiosk';
  title.textContent = renderedState.title;
  message.textContent = shouldAutoReset
    ? 'Kiosk reset complete. Align face inside the guide to begin the next scan.'
    : status.message || 'Waiting for camera activity.';
  code.textContent = (status.state || 'IDLE').toUpperCase();
  hint.textContent = renderedState.hint;
  setActiveVisualState(renderedState.visualState);
}

function pollKioskStatus() {
  const refresh = () => {
    fetch('/api/public/status')
      .then((res) => res.json())
      .then((json) => {
        if (!json.success || !json.data) return;
        renderKioskStatus(json.data);
      })
      .catch(() => {
        // Ignore temporary network interruptions.
      });
  };

  refresh();
  setInterval(refresh, 2000);
}

function watchFeed() {
  const img = document.getElementById('webcam-feed');
  if (!img) return;

  img.addEventListener('error', () => {
    setTimeout(() => {
      const streamBase = img.dataset.streamUrl || '/stream';
      const mode = img.dataset.mode || currentMode;
      img.src = `${streamBase}?mode=${mode}&t=${Date.now()}`;
    }, 3000);
  });
}

function startRealtimeUpdates() {
  if (realtimeStarted) return;
  realtimeStarted = true;
  pollRecentRecognitions();
  pollKioskStatus();
  watchFeed();
}

function showDetection(mode) {
  currentMode = mode;
  const area = document.getElementById('detection-area');
  const buttons = document.querySelectorAll('.action-btn');
  const chip = document.getElementById('mode-chip');
  const img = document.getElementById('webcam-feed');
  const idle = document.getElementById('feed-idle');
  const title = document.getElementById('status-state-title');
  const message = document.getElementById('scan-status-message');
  const code = document.getElementById('status-state-code');
  const hint = document.getElementById('status-short-hint');
  const banner = document.getElementById('status-banner');
  const label = document.getElementById('status-state-label');

  if (area) area.classList.remove('detection-hidden');

  buttons.forEach((button) => {
    if (!(button instanceof HTMLElement)) return;
    button.classList.toggle('active', button.dataset.mode === mode);
  });

  if (chip) {
    chip.textContent = mode === 'check-out' ? 'Check Out Active' : 'Check In Active';
    chip.classList.add('show');
  }

  if (img instanceof HTMLImageElement) {
    const streamBase = img.dataset.streamUrl || '/stream';
    img.dataset.mode = mode;
    img.src = `${streamBase}?mode=${mode}&t=${Date.now()}`;
    img.classList.remove('feed-image-hidden');
  }

  if (idle) {
    idle.style.display = 'none';
  }

  if (banner) {
    banner.classList.remove('neutral', 'info', 'ok', 'warn', 'error');
    banner.classList.add('info');
  }

  if (label) {
    label.textContent = mode === 'check-out' ? 'Check Out Kiosk' : 'Check In Kiosk';
  }

  if (title) {
    title.textContent = mode === 'check-out' ? 'Ready for check out scan' : 'Ready for check in scan';
  }

  if (message) {
    message.textContent = 'Align your face in the guide, look at the camera, and wait for automatic verification.';
  }

  if (code) {
    code.textContent = 'STREAM_STARTED';
  }

  if (hint) {
    hint.textContent = 'Align face in guide';
  }

  setActiveVisualState('align-face');
  startRealtimeUpdates();
}

function initModePicker() {
  const buttons = document.querySelectorAll('.action-btn');
  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      if (!(button instanceof HTMLElement)) return;
      showDetection(button.dataset.mode || 'check-in');
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  startClock();
  initModePicker();
});
