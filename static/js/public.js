'use strict';

let realtimeStarted = false;

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

function watchFeed() {
  const img = document.getElementById('webcam-feed');
  if (!img) return;

  img.addEventListener('error', () => {
    setTimeout(() => {
      const streamBase = img.dataset.streamUrl || '/stream';
      const mode = img.dataset.mode || 'check-in';
      img.src = `${streamBase}?mode=${mode}&t=${Date.now()}`;
    }, 3000);
  });
}

function startRealtimeUpdates() {
  if (realtimeStarted) return;
  realtimeStarted = true;
  pollRecentRecognitions();
  watchFeed();
}

function showDetection(mode) {
  const area = document.getElementById('detection-area');
  const buttons = document.querySelectorAll('.action-btn');
  const chip = document.getElementById('mode-chip');
  const img = document.getElementById('webcam-feed');
  const idle = document.getElementById('feed-idle');

  if (area) area.classList.remove('detection-hidden');

  buttons.forEach((button) => {
    if (!(button instanceof HTMLElement)) return;
    button.classList.toggle('active', button.dataset.mode === mode);
  });

  if (chip) {
    const text = mode === 'check-out' ? 'Mode: Check Out' : 'Mode: Check In';
    chip.textContent = text;
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

  startRealtimeUpdates();
}

function initModePicker() {
  const buttons = document.querySelectorAll('.action-btn');
  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      if (!(button instanceof HTMLElement)) return;
      const mode = button.dataset.mode || 'check-in';
      showDetection(mode);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initModePicker();
});
