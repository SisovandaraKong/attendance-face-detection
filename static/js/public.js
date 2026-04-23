'use strict';

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
      img.src = '/stream?t=' + Date.now();
    }, 3000);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  pollRecentRecognitions();
  watchFeed();
});
