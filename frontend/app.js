/* ─────────────────────────────────────────────────────────────────────
   app.js — PodcastShorts AI Clean 1-Click Generation & Gallery Logic
   Handles: 1-click YouTube link generation, live progress monitoring,
   automatic video filter & pitch shifting status, responsive 9:16 gallery,
   and instant modal preview & download.
───────────────────────────────────────────────────────────────────── */

function getApiBase() {
  const saved = localStorage.getItem('CUSTOM_API_BASE');
  if (saved) return saved;

  if (
    !window.location.origin ||
    window.location.origin === 'null' ||
    window.location.protocol === 'file:' ||
    window.location.hostname.includes('github.io') ||
    window.location.port === '5500' ||
    window.location.port === '3000' ||
    window.location.port === '5173'
  ) {
    return 'http://localhost:5000';
  }
  return window.location.origin;
}

let API_BASE = getApiBase();

let allRenderedClips = [];
let pollInterval = null;

window.promptBackendUrl = function() {
  const current = localStorage.getItem('CUSTOM_API_BASE') || API_BASE;
  const input = prompt(
    'Enter your Backend API Server URL (e.g. http://localhost:5000, or your live Render/Railway URL):',
    current
  );
  if (input !== null) {
    const trimmed = input.trim().replace(/\/+$/, '');
    if (trimmed) {
      localStorage.setItem('CUSTOM_API_BASE', trimmed);
      API_BASE = trimmed;
    } else {
      localStorage.removeItem('CUSTOM_API_BASE');
      API_BASE = getApiBase();
    }
    checkBackendHealth();
    refreshOutputs();
    showToast(`Backend set to: ${API_BASE}`, 'info');
  }
};

// ── Document Ready Initialization ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkBackendHealth();
  refreshOutputs();

  // Check URL query parameters (e.g. index.html?url=https://...)
  const urlParams = new URLSearchParams(window.location.search);
  const passedUrl = urlParams.get('url');
  if (passedUrl) {
    const input = document.getElementById('ytUrl');
    if (input) input.value = decodeURIComponent(passedUrl);
  }

  // Poll backend health periodically
  setInterval(checkBackendHealth, 4000);
});

// ── Backend Health Check ──────────────────────────────────────────────
async function checkBackendHealth() {
  const dot = document.getElementById('serverDot');
  const lbl = document.getElementById('serverLbl');
  
  const endpointsToTry = [
    `${API_BASE}/api/status`,
    'http://localhost:5000/api/status',
    'http://127.0.0.1:5000/api/status'
  ];

  for (const ep of endpointsToTry) {
    try {
      const res = await fetch(ep, { cache: 'no-store' });
      if (res.ok) {
        if (dot) dot.className = 'status-dot green';
        if (lbl) lbl.textContent = 'Backend Connected';
        API_BASE = ep.replace('/api/status', '');
        return;
      }
    } catch (e) {
      // Continue to next endpoint
    }
  }

  if (dot) dot.className = 'status-dot';
  if (lbl) lbl.textContent = 'Backend Offline';
}

// ── 1-Click Auto Generation ───────────────────────────────────────────
window.startAutoGenerate = async function() {
  const url = document.getElementById('ytUrl')?.value.trim();

  if (!url) {
    showToast('Please paste a YouTube link to generate shorts.', 'error');
    document.getElementById('ytUrl')?.focus();
    return;
  }

  const btn = document.getElementById('autoGenerateBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="status-indicator-spinner" style="width:18px;height:18px;border-width:2px;"></span> Generating...`;
  }

  const monitorCard = document.getElementById('pipelineMonitorCard');
  if (monitorCard) {
    monitorCard.style.display = 'block';
    monitorCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  showToast('🚀 Pipeline started! Generating shorts for full video...', 'info');

  const payload = {
    url: url,
    num_shorts: 'all',
  };

  let targetBase = API_BASE || window.location.origin || 'http://localhost:5000';
  if (!targetBase || targetBase === 'null' || targetBase.startsWith('file:')) {
    targetBase = 'http://localhost:5000';
  }

  try {
    const res = await fetch(`${targetBase}/api/pipeline/auto-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      pollPipelineProgress();
    } else {
      showToast(`Pipeline: ${data.message || 'Error'}`, 'error');
      resetGenerateBtn();
    }
  } catch (err) {
    showToast(`Cannot reach backend at ${targetBase}. Tap "Backend Offline" at the top to connect to your computer or cloud backend!`, 'error');
    resetGenerateBtn();
  }
};

function resetGenerateBtn() {
  const btn = document.getElementById('autoGenerateBtn');
  if (btn) {
    btn.disabled = false;
    btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Generate Shorts`;
  }
}

function pollPipelineProgress() {
  if (pollInterval) clearInterval(pollInterval);

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (!res.ok) return;
      const data = await res.json();
      const p = data.pipeline;
      if (!p) return;

      const progressBar = document.getElementById('monitorProgressBar');
      const phaseText   = document.getElementById('monitorPhaseText');
      const percentText = document.getElementById('monitorPercentText');
      const logBox      = document.getElementById('monitorLiveLog');
      const monitorCard = document.getElementById('pipelineMonitorCard');
      const title       = document.getElementById('monitorTitle');
      const subtitle    = document.getElementById('monitorSubtitle');
      const spinner     = document.getElementById('monitorSpinner');

      if (progressBar) progressBar.style.width = (p.progress || 5) + '%';
      if (percentText) percentText.textContent  = (p.progress || 5) + '%';

      const phaseDescriptions = {
        download:  'Phase 1/5: Downloading high-quality video...',
        transcribe:'Phase 2/5: Transcribing speech / analyzing video stream...',
        select:    'Phase 3/5: Selecting viral & high-energy highlight moments...',
        rank:      'Phase 4/5: Ranking best candidate clips...',
        render:    'Phase 5/5: Reframing 9:16, applying cinematic color & voice pitch polish...',
      };

      if (phaseText && p.current_phase) {
        phaseText.textContent = phaseDescriptions[p.current_phase] || 'Generating viral shorts...';
      }

      if (logBox && p.logs && p.logs.length > 0) {
        logBox.textContent = p.logs.join('\n');
        logBox.scrollTop = logBox.scrollHeight;
      }

      // ── COMPLETED ──────────────────────────────────────────────────
      if (p.status === 'completed') {
        clearInterval(pollInterval);

        // Fill progress to 100%
        if (progressBar) progressBar.style.width = '100%';
        if (percentText) percentText.textContent  = '100%';

        // Update card to "Done" state
        if (spinner)   spinner.style.display = 'none';
        if (title)     title.textContent     = '✅ All Shorts Generated!';
        if (subtitle)  subtitle.textContent  = 'Your viral 9:16 shorts are ready in the gallery below.';
        if (phaseText) phaseText.textContent  = '✓ Pipeline complete — rendering done';

        showToast('🎉 Shorts generated! Loading gallery...', 'success');
        resetGenerateBtn();

        // Load gallery with newly created clips
        await refreshOutputs();

        // Auto-hide the progress card after a short delay, then scroll to gallery
        setTimeout(() => {
          if (monitorCard) {
            monitorCard.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            monitorCard.style.opacity = '0';
            monitorCard.style.transform = 'translateY(-12px)';
            setTimeout(() => {
              monitorCard.style.display = 'none';
              monitorCard.style.opacity = '';
              monitorCard.style.transform = '';
              monitorCard.style.transition = '';
            }, 500);
          }
          // Scroll to gallery
          const gallery = document.getElementById('gallerySection');
          if (gallery) gallery.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 1800);

      // ── ERROR ───────────────────────────────────────────────────────
      } else if (p.status === 'error') {
        clearInterval(pollInterval);

        if (spinner)   spinner.style.display = 'none';
        if (title)     title.textContent     = '❌ Generation Failed';
        if (subtitle)  subtitle.textContent  = p.error || 'An error occurred. Check logs below.';
        if (progressBar) progressBar.style.background = 'var(--error, #ef4444)';

        showToast('Pipeline error: ' + (p.error || 'Unknown error'), 'error');
        resetGenerateBtn();

        // Auto-hide error card after 6s
        setTimeout(() => {
          if (monitorCard) {
            monitorCard.style.transition = 'opacity 0.5s ease';
            monitorCard.style.opacity = '0';
            setTimeout(() => {
              monitorCard.style.display = 'none';
              monitorCard.style.opacity = '';
              monitorCard.style.transition = '';
              // Reset card internals for next run
              if (spinner)  spinner.style.display = '';
              if (title)    title.textContent     = 'Generating Your Viral Shorts...';
              if (subtitle) subtitle.textContent  = 'AI is extracting highlights, tracking faces, auto-grading color & voice pitch, and burning captions.';
              if (progressBar) progressBar.style.background = '';
            }, 500);
          }
        }, 6000);
      }
    } catch (e) {
      // ignore transient fetch errors
    }
  }, 1000);
}


// ── Outputs Gallery ───────────────────────────────────────────────────
window.refreshOutputs = async function() {
  try {
    let res = await fetch(`${API_BASE}/api/files/output`);
    if (!res.ok) {
      res = await fetch(`${API_BASE}/api/outputs`);
    }
    if (!res.ok) return;
    const data = await res.json();
    allRenderedClips = data.files || data.outputs || [];
    renderGalleryGrid(allRenderedClips);
  } catch (err) {
    console.error('Failed to load outputs:', err);
  }
};

function renderGalleryGrid(clips) {
  const grid = document.getElementById('clipsGrid');
  if (!grid) return;

  if (!clips || clips.length === 0) {
    grid.innerHTML = `
      <div style="grid-column:1/-1; text-align:center; padding:3.5rem 1rem; color:var(--text-muted); background:var(--bg-card); border:1px dashed var(--border); border-radius:var(--radius);">
        <div style="font-size:3rem; margin-bottom:0.75rem;">🎬</div>
        <p style="font-size:1.2rem; font-weight:700; color:var(--text); margin-bottom:0.25rem;">No Generated Shorts Yet</p>
        <p style="font-size:0.9rem; max-width:480px; margin:0 auto;">Paste any YouTube link above and click <strong>Generate Shorts</strong> to automatically create viral 9:16 clips.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = clips.map((clip, idx) => {
    const filename = clip.name || clip.filename;
    const videoSrc = `${API_BASE}/api/stream/output/${filename}`;
    const rankNum  = idx + 1;
    const sizeStr  = clip.size_mb ? `${clip.size_mb.toFixed(1)} MB` : '';

    return `
      <div class="clip-card" style="opacity:0;transform:translateY(24px);transition:opacity 0.45s ease ${idx * 80}ms, transform 0.45s ease ${idx * 80}ms;" onclick="openVideoModal('${filename}')">
        <div class="clip-thumb">
          <video src="${videoSrc}#t=0.5" preload="metadata" muted playsinline></video>
          <span class="clip-duration">9:16 HD</span>
          <div class="clip-play-overlay">▶</div>
        </div>
        <div class="clip-info">
          <span class="clip-rank">✨ Short #${rankNum}</span>
          <span class="clip-score">${sizeStr}</span>
        </div>
        <div class="clip-actions">
          <button class="clip-btn primary" onclick="event.stopPropagation(); openVideoModal('${filename}')">
            ▶ Preview
          </button>
          <a class="clip-btn" href="${videoSrc}" download="${filename}" onclick="event.stopPropagation()">
            ⬇️ Save
          </a>
          <button class="clip-btn" style="color:#f87171; max-width:40px; padding:0.4rem;" title="Delete short" onclick="event.stopPropagation(); deleteSingleOutput('${filename}')">
            🗑️
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Trigger the staggered pop-in by forcing a reflow then setting final state
  requestAnimationFrame(() => {
    grid.querySelectorAll('.clip-card').forEach(card => {
      requestAnimationFrame(() => {
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
      });
    });
  });
}




window.clearAllOutputs = async function() {
  if (!confirm('Are you sure you want to delete all generated shorts?')) return;
  try {
    const res = await fetch(`${API_BASE}/api/files/output/clear`, { method: 'POST' });
    if (res.ok) {
      showToast('All shorts cleared', 'success');
      refreshOutputs();
    }
  } catch (err) {
    showToast('Failed to clear outputs', 'error');
  }
};

window.deleteSingleOutput = async function(filename) {
  if (!confirm(`Delete ${filename}?`)) return;
  try {
    const res = await fetch(`${API_BASE}/api/files/output/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    });
    if (res.ok) {
      showToast(`Deleted ${filename}`, 'success');
      refreshOutputs();
    }
  } catch (err) {
    showToast(`Failed to delete ${filename}`, 'error');
  }
};

// ── Modal Video Player ────────────────────────────────────────────────
window.openVideoModal = function(filename) {
  const modal = document.getElementById('videoModal');
  const player = document.getElementById('modalVideoPlayer');
  const title = document.getElementById('modalVideoTitle');
  const dlBtn = document.getElementById('modalDownloadBtn');
  
  if (!modal || !player) return;

  const videoUrl = `${API_BASE}/api/stream/output/${filename}`;
  player.src = videoUrl;
  player.load();
  player.play().catch(() => {});

  if (title) title.textContent = filename;
  if (dlBtn) {
    dlBtn.href = videoUrl;
    dlBtn.download = filename;
  }

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
};

window.closeVideoModal = function(e) {
  if (e && e.target && e.target.id !== 'videoModal' && !e.target.classList.contains('modal-close-btn')) {
    return;
  }
  const modal = document.getElementById('videoModal');
  const player = document.getElementById('modalVideoPlayer');
  if (player) {
    player.pause();
    player.src = '';
  }
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = 'auto';
};

// ── Toast Notifications ───────────────────────────────────────────────
window.showToast = function(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
};
