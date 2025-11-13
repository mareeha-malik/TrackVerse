(async function(){
  console.log("=== DASHBOARD INIT ===");
  
  const token = localStorage.getItem("tv_token");
  console.log("Token exists:", !!token);
  console.log("Token value:", token ? token.substring(0, 50) + "..." : "null");
  
  if (!token) {
    console.log("No token found, redirecting to login");
    window.location.href = "/login";
    return;
  }

  function showNotif(msg) {
    console.log("Notification:", msg);
    const box = document.getElementById("notifBox") || (()=> {
      const b = document.createElement("div");
      b.id = "notifBox";
      b.style.position = "fixed";
      b.style.top = "10px";
      b.style.right = "10px";
      b.style.zIndex = 1050;
      document.body.appendChild(b);
      return b;
    })();
    const el = document.createElement("div");
    el.className = "alert alert-info py-1";
    el.textContent = msg;
    box.prepend(el);
    setTimeout(()=> el.remove(), 7000);
  }

  // setup socket for notifications (non-blocking)
  let socket = null;
  let currentUserId = null;
  try {
    console.log("Initializing socket connection...");
  // prefer auth in options for modern socket.io servers; force polling in dev to avoid raw websocket upgrades
  socket = io({ transports: ["polling"], auth: { token } });
  // expose the socket globally so site scripts can reuse it
  try { window.__siteSocket = socket; } catch (e) {}
    socket.on("connect", () => {
      console.log("✓ Dashboard socket connected");
    });
    socket.on("connect_error", (err) => {
      console.error("Socket connection error:", err);
    });
    socket.on("bug_created", (data) => {
      showNotif(`New bug: ${data.title} (#${data.bug_id})`);
    });
    socket.on("bug_assigned", (data) => {
      showNotif(`Bug #${data.bug_id} assigned to ${data.assignee_name}`);
      // if assigned to current user, refresh the assigned list
      try {
        if (currentUserId && Number(data.assignee_id) === Number(currentUserId)) {
          loadAssignedBugs();
        }
      } catch (err) { console.warn('assigned handler error', err); }
    });
    socket.on("bug_resolved", (data) => {
      showNotif(`Bug #${data.bug_id} marked ${data.status}`);
      try {
        if (currentUserId && Number(data.assignee_id) === Number(currentUserId)) {
          loadAssignedBugs();
        }
      } catch (err) { console.warn('resolved handler error', err); }
    });
  } catch (e) {
    console.error("Socket init failed:", e);
  }

  async function getJSON(url) {
    console.log(`Fetching: ${url}`);
    try {
      const res = await fetch(url, {
        headers: {"Authorization": "Bearer " + token}
      });
      
      console.log(`Response from ${url}: status=${res.status}`);
      
      if (!res.ok) {
        // If auth-related, force login
        if (res.status === 401 || res.status === 422) {
          console.error("Auth failed, clearing token and redirecting");
          localStorage.removeItem("tv_token");
          window.location.href = "/login";
          return null;
        }
        // For other errors, show a message and return null (do not redirect)
        const text = await res.text().catch(()=>res.statusText || "error");
        console.error(`Request failed (${res.status}):`, text);
        showNotif(`Request failed (${res.status}): ${text}`);
        return null;
      }
      
      const data = await res.json();
      console.log(`Data from ${url}:`, data);
      return data;
    } catch (err) {
      // network-level error: inform user but don't clear token
      console.error("Network error:", err);
      showNotif("Network error while fetching data. Try again.");
      return null;
    }
  }

  // Load current user and assigned bugs
  async function getCurrentUser() {
    const me = await getJSON('/api/auth/me');
    // /api/auth/me may return { user: { id: ... } } or { id: ... }
    const uid = me && (me.id || (me.user && me.user.id));
    if (uid) {
      currentUserId = uid;
      window.__currentUserId = currentUserId;
      console.log('Current user id:', currentUserId);
    }
    debug('getCurrentUser -> ' + JSON.stringify(me));
    return me;
  }

  async function loadAssignedBugs() {
    if (!currentUserId) {
      console.log('No current user yet, skipping assigned load');
      debug('No current user yet, skipping assigned load');
      return;
    }
    const url = `/api/bugs?assignee_id=${encodeURIComponent(currentUserId)}`;
    console.log('loadAssignedBugs fetching:', url);
    debug('fetching: ' + url);
    const data = await getJSON(url);
    console.log('loadAssignedBugs got:', data);
    debug('response: ' + JSON.stringify(data));
    const list = data && data.bugs ? data.bugs : (Array.isArray(data) ? data : []);
    renderAssignedList(list);
  }

  function renderAssignedList(bugs) {
    const container = document.getElementById('assignedList');
    if (!container) return;
    container.innerHTML = '';
    if (!bugs || bugs.length === 0) {
      container.textContent = 'No bugs assigned to you.';
      // update badge to hidden/zero
      try { updateAssignedBadge(0); } catch(e){}
      return;
    }
    const ul = document.createElement('ul');
    ul.className = 'list-unstyled mb-0';
    bugs.forEach(b => {
      const li = document.createElement('li');
      li.innerHTML = `<a href="/bugs/${b.id}" class="text-light">#${b.id}</a> — ${escapeHtml(b.title)} <span class="badge bg-secondary ms-2">${b.status}</span>`;
      ul.appendChild(li);
    });
    container.appendChild(ul);
    try { updateAssignedBadge(bugs.length); } catch(e){}
  }

  function updateAssignedBadge(count) {
    const el = document.getElementById('assignedBadge');
    if (!el) return;
    if (!count || count === 0) {
      el.classList.add('d-none');
      el.textContent = '0';
    } else {
      el.classList.remove('d-none');
      el.textContent = String(count);
    }
  }

  // on-page debug output (visible only when set)
  function debug(msg){
    try{
      const el = document.getElementById('assignedDebug');
      if (!el) return;
      el.style.display = 'block';
      const now = new Date().toISOString();
      el.textContent = `${now} - ${msg}\n` + el.textContent;
    }catch(e){ console.warn('debug write failed', e); }
  }

  // simple escape helper
  function escapeHtml(s){
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  // wire the refreshAssigned button (if present)
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('refreshAssigned');
    if (btn) btn.addEventListener('click', () => loadAssignedBugs());
  });

  // bootstrap assigned list: fetch current user first, then assigned bugs
  try {
    await getCurrentUser();
    await loadAssignedBugs();

    console.log("Fetching analytics summary...");
    const data = await getJSON("/api/bugs/analytics/summary");
    
    if (!data) {
      console.warn("No data returned from analytics API");
      // API failed but not auth — keep dashboard visible
      return;
    }
    
    console.log("Analytics data received:", data);
    
    document.getElementById("totalProjects").textContent = data.total_projects || 0;
    document.getElementById("totalBugs").textContent = data.total_bugs || 0;
    document.getElementById("totalUsers").textContent = data.total_users || 0;

    // Pie chart for status
    if (data.by_status) {
      const statusLabels = Object.keys(data.by_status);
      const statusValues = statusLabels.map(k => data.by_status[k]);
      console.log("Creating chart with labels:", statusLabels, "values:", statusValues);
      
      const ctx = document.getElementById("statusChart").getContext("2d");
      new Chart(ctx, {
        type: "pie",
        data: {
          labels: statusLabels,
          datasets: [{data: statusValues, backgroundColor: ["#dc3545","#ffc107","#0d6efd","#198754"]}]
        }
      });
    }

    // recent table
    const tbody = document.querySelector("#recentTable tbody");
    const recentBugs = data.recent || [];
    console.log("Rendering recent bugs:", recentBugs.length);
    
    recentBugs.forEach(r => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${r.id}</td><td>${r.title}</td><td>${r.status}</td><td>${new Date(r.created_at).toLocaleString()}</td>`;
      tbody.appendChild(tr);
    });
    
    console.log("=== DASHBOARD LOADED SUCCESSFULLY ===");
  } catch (e) {
    console.error("Dashboard error:", e);
    console.error("Error stack:", e.stack);
    // Only redirect if explicitly unauthorized; otherwise keep UI and notify
    showNotif("Unexpected error loading dashboard.");
  }
})();

// safe helper to avoid "Cannot redefine property: href" errors
(function (global) {
    // Provide safeGetHref / safeSetHref helpers for the rest of your dashboard code.
    // Use these instead of directly calling Object.defineProperty(window.location, 'href', ...)
    function safeGetHref() {
        try {
            return window.location.href;
        } catch (e) {
            // fallback to stored value
            return global._safeHref || '';
        }
    }

    function safeSetHref(val) {
        try {
            // prefer direct assignment (does not attempt to redefine the property)
            window.location.href = val;
        } catch (e) {
            // if assignment fails for some reason, store on a safe custom property
            global._safeHref = String(val);
        }
    }

    // Attempt to create a getter/setter on window.location only if it's allowed
    try {
        var desc = Object.getOwnPropertyDescriptor(window.location, 'href');
        if (!desc || desc.configurable) {
            Object.defineProperty(window.location, 'href', {
                get: function () { return safeGetHref(); },
                set: function (v) { safeSetHref(v); },
                configurable: true,
                enumerable: true
            });
        } else {
            // Can't redefine; ensure a safe fallback exists
            if (typeof global._safeHref === 'undefined') {
                global._safeHref = window.location && window.location.href ? window.location.href : '';
            }
        }
    } catch (err) {
        // Some environments (older browsers / CSP) will throw — fallback silently
        if (typeof global._safeHref === 'undefined') {
            try { global._safeHref = window.location && window.location.href ? window.location.href : ''; } catch (e) { global._safeHref = ''; }
        }
        console.warn('dashboard: could not redefine location.href, using safe fallback.', err);
    }

    // Expose helpers for other modules in the dashboard
    global.dashboardHref = {
        get: safeGetHref,
        set: safeSetHref
    };

    // ...existing code...
})(window);