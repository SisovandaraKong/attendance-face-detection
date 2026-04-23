/**
 * static/js/main.js
 * Minimal vanilla JS — only what HTML/CSS can't do alone.
 *
 * Responsibilities:
 *   1. Live clock in the topbar
 *   2. Auto-refresh the attendance sidebar on the dashboard every 5 s
 *   3. Date-filter navigation on the attendance page
 *   4. Webcam feed error/reconnect handling
 */

'use strict';

// ── Live clock ────────────────────────────────────────────
function startClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  const tick = () => {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-GB');
  };
  tick();
  setInterval(tick, 1000);
}

// ── Auto-refresh today's attendance sidebar ───────────────
// Polls /attendance/api/records every 5 s and rebuilds the list
// so the operator can watch entries appear in real time.
function startAttendancePoller(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const refresh = () => {
    const today = new Date().toISOString().slice(0, 10);
    fetch(`/attendance/api/records?date=${today}`)
      .then(r => r.json())
      .then(json => {
        if (!json.success) return;
        const records = json.data.slice(-10).reverse(); // newest first
        if (records.length === 0) {
          container.innerHTML = '<p class="text-muted text-sm" style="padding:16px">No records yet today.</p>';
          return;
        }
        container.innerHTML = records.map(r => `
          <div class="record-item">
            <div class="record-avatar">${r.name.charAt(0).toUpperCase()}</div>
            <div class="record-info">
              <div class="record-name">${r.name}</div>
              <div class="record-time">${r.time}</div>
            </div>
            <span class="badge-present">Present</span>
          </div>
        `).join('');

        // Update the count badge if present
        const countEl = document.getElementById('today-count');
        if (countEl) countEl.textContent = json.data.length;
      })
      .catch(() => { /* Network blip — skip silently, retry next tick */ });
  };

  refresh();
  setInterval(refresh, 5000);
}

// ── Webcam feed reconnect ─────────────────────────────────
// If the MJPEG stream drops (e.g. webcam unplugged), the <img>
// fires an error event. We reload the src attribute after 3 s.
function watchFeed(imgId) {
  const img = document.getElementById(imgId);
  if (!img) return;
  img.addEventListener('error', () => {
    console.warn('Feed lost — reconnecting in 3 s…');
    setTimeout(() => {
      img.src = img.src.split('?')[0] + '?t=' + Date.now();
    }, 3000);
  });
}

// ── Date selector navigation (attendance page) ────────────
// Redirect to /attendance/?date=<selected> when user picks a date.
function initDateSelector(selectId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  sel.addEventListener('change', () => {
    window.location.href = `/attendance/?date=${sel.value}`;
  });
}

// ── Boot ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  startClock();
  startAttendancePoller('attendance-sidebar');
  watchFeed('webcam-feed');
  initDateSelector('date-selector');
});
