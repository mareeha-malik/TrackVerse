(async function(){
  if (window.__siteSocketInit) return;
  window.__siteSocketInit = true;

  const token = localStorage.getItem('tv_token');
  if (!token) return;

  async function ensureIo(){
    if (window.io) return;
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.socket.io/4.5.4/socket.io.min.js';
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  try { await ensureIo(); } catch(e) {
    console.warn('site_socket: failed to load socket.io client', e);
    return;
  }

  const socket = window.__siteSocket || io({ transports: ["polling"], auth: { token } });
  window.__siteSocket = socket;

  async function getCurrentUserId(){
    if (window.__currentUserId) return window.__currentUserId;
    try {
      const res = await fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + token } });
      if (!res.ok) return null;
      const body = await res.json();
      const id = body?.id || body?.user?.id;
      if (id) window.__currentUserId = id;
      return id;
    } catch(e) {
      console.warn('getCurrentUserId failed', e);
      return null;
    }
  }

  async function updateAssignedSection(){
    const badgeEl = document.getElementById('assignedBadge');
    const listEl = document.getElementById('assignedList');
    if (!badgeEl || !listEl) return;

    listEl.textContent = 'Loading...';

    try {
      const uid = await getCurrentUserId();
      if (!uid) {
        listEl.textContent = 'Unable to get user info.';
        return;
      }

      const url = `/api/bugs?assignee_id=${encodeURIComponent(uid)}`;
      const res = await fetch(url, { headers: { 'Authorization': 'Bearer ' + token } });

      if (!res.ok) {
        listEl.textContent = 'Failed to load assigned bugs.';
        return;
      }

      const body = await res.json();
      const bugs = body?.bugs || (Array.isArray(body) ? body : []);

      // Badge update
      if (!bugs.length) {
        badgeEl.classList.add('d-none');
        badgeEl.textContent = '0';
        listEl.textContent = 'No bugs assigned to you.';
        return;
      }

      badgeEl.classList.remove('d-none');
      badgeEl.textContent = String(bugs.length);

      // Populate assignedList
      listEl.innerHTML = bugs.map(bug => `
        <div class="border-bottom py-1">
          <span class="text-info fw-semibold">#${bug.id}</span>
          ${bug.title ? ` - ${bug.title}` : ''}
          <span class="text-secondary small">(${bug.status || 'Open'})</span>
        </div>
      `).join('');

    } catch(e) {
      console.warn('updateAssignedSection failed', e);
      listEl.textContent = 'Error loading assigned bugs.';
    }
  }

  // Expose manual refresh
  window.__updateAssignedSection = updateAssignedSection;

  // Socket events
  socket.on('connect', updateAssignedSection);
  socket.on('bug_assigned', updateAssignedSection);
  socket.on('bug_resolved', updateAssignedSection);

  // Add manual refresh button listener
  const refreshBtn = document.getElementById('refreshAssigned');
  if (refreshBtn) refreshBtn.addEventListener('click', updateAssignedSection);
})();
