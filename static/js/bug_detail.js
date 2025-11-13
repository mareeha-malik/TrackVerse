(function(){
  const token = localStorage.getItem("tv_token");
  if (!token) { location.href = "/login"; return; }
  const bugId = window.TV_BUG_ID;
  // small html-escape helper (local fallback)
  function escapeHtml(s){ if (s==null) return ''; return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function authHeaders() { return { "Authorization": "Bearer " + token, "Content-Type":"application/json" }; }

  let socket = null;
  try {
  socket = io({ transports: ["polling"], query: { token } });
    socket.on("connect", ()=> console.debug("bug_detail socket connected"));
    socket.on("bug_assigned", (data) => {
      if (data.bug_id === bugId) showNotif(`Assigned to ${data.assignee_name}`);
    });
    socket.on("bug_resolved", (data) => {
      if (data.bug_id === bugId) showNotif(`Status: ${data.status}`);
    });
  } catch (e) {
    console.debug("socket init failed", e);
  }

  function showNotif(msg) {
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

  async function loadBug() {
    const res = await fetch("/api/bugs/" + bugId, {headers: {"Authorization":"Bearer "+token}});
    if (!res.ok) { localStorage.removeItem("tv_token"); location.href="/login"; return; }
    const b = await res.json();
    // join project room so this page receives project-level events
    if (socket && b.project_id) socket.emit("join_project", { project_id: b.project_id });
    const container = document.getElementById("bugContainer");
    container.innerHTML = `<div class="card p-3">
      <h4>${b.title} <small class="text-muted">#${b.id}</small></h4>
      <div class="mb-2">${b.description || ""}</div>
      <div class="small text-muted">Severity: ${b.severity} · Priority: ${b.priority}</div>
      <div class="d-flex align-items-center gap-2 mt-2">
        <label class="mb-0 small text-muted">Status</label>
        <select id="bug_status" class="form-select form-select-sm" style="width:170px">
          <option value="Open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
          <option value="wontfix">Wontfix</option>
        </select>
        <label class="mb-0 small text-muted">Assignee</label>
        <select id="bug_assignee_select" class="form-select form-select-sm" style="width:220px">
          <option value="">Unassigned</option>
        </select>
        <button id="saveBugChanges" class="btn btn-sm btn-primary">Save</button>
      </div>
      <hr>
      <div><strong>Attachments</strong><ul>${b.attachments.map(a=>`<li><a href="/api/bugs/${b.id}/attachments/${a.id}">${a.filename}</a></li>`).join("")}</ul></div>
    </div>`;
    // prefill status
    try { document.getElementById('bug_status').value = b.status || 'Open'; } catch(e){}
    // populate assignee select
    populateAssigneeSelect().then(()=>{
      try { document.getElementById('bug_assignee_select').value = b.assignee_id || (b.assignee && (b.assignee.id || b.assignee._id)) || ''; } catch(e){}
    });
    const comments = document.getElementById("commentsList");
    comments.innerHTML = b.comments.map(c=>`<div class="mb-2"><strong>${c.user}</strong> <small class="text-muted">${new Date(c.created_at).toLocaleString()}</small><div>${c.body}</div></div>`).join("");
  }

  document.getElementById("commentForm").addEventListener("submit", async (e)=>{
    e.preventDefault();
    const body = document.getElementById("commentBody").value;
    if (!body) return;
    const res = await fetch(`/api/bugs/${bugId}/comment`, {method:"POST", headers: authHeaders(), body: JSON.stringify({body})});
    if (res.ok) {
      document.getElementById("commentBody").value = "";
      loadBug();
    }
  });

  // fetch users and populate assignee select
  async function populateAssigneeSelect() {
    const endpoints = ['/api/users','/api/auth/users','/api/users/list','/api/bugs/users'];
    let list = [];
    let lastErr = null;
    for (const ep of endpoints) {
      try {
        const res = await fetch(ep, { headers: { 'Authorization': 'Bearer ' + token } });
        if (!res.ok) {
          lastErr = `${ep} -> ${res.status}`;
          continue;
        }
        const body = await res.json();
        if (Array.isArray(body)) list = body;
        else if (Array.isArray(body.users)) list = body.users;
        else if (Array.isArray(body.data)) list = body.data;
        else if (Array.isArray(body.results)) list = body.results;
        else if (body && typeof body === 'object' && body.users) list = body.users;
        else if (body && typeof body === 'object') {
          // try a fallback: look for top-level array-like keys
          const vals = Object.values(body).find(v => Array.isArray(v));
          if (vals) list = vals;
        }
        if (list && list.length) {
          // normalize minimal shape
          list = list.map(u => ({ id: u.id || u.user_id || u._id || u.uid, name: u.name || u.email || ('User '+(u.id||u.user_id||'')), email: u.email }));
          break;
        }
      } catch (e) {
        lastErr = e;
      }
    }

    const sel = document.getElementById('bug_assignee_select');
    if (!sel) return list;
    try {
      // always include Unassigned option
      const opts = ['<option value="">Unassigned</option>'];
      // sort alphabetically by name
      list.sort((a,b)=> String(a.name||'').localeCompare(String(b.name||'')));
      for (const u of list) {
        if (!u || (typeof u.id === 'undefined' && typeof u.user_id === 'undefined' && typeof u._id === 'undefined')) continue;
        const id = u.id || u.user_id || u._id || u.uid;
        const label = u.name || u.email || (`User ${id}`);
        opts.push(`<option value="${escapeHtml(String(id))}">${escapeHtml(String(label))}</option>`);
      }
      sel.innerHTML = opts.join('');
    } catch (e) {
      console.warn('populateAssigneeSelect render failed', e);
    }

    if ((!list || list.length === 0) && lastErr) {
      try { showNotif('Could not load users for assignment.'); } catch(e){}
      console.warn('populateAssigneeSelect: no users loaded', lastErr);
    }
    return list;
  }

  // save status/assignee changes
  try {
    document.addEventListener('click', async function(ev){
      if (ev.target && ev.target.id === 'saveBugChanges') {
        const status = document.getElementById('bug_status').value;
        const assignee = document.getElementById('bug_assignee_select').value || null;
        const payload = { status };
        if (assignee) payload.assignee_id = Number(assignee);
        try {
          const r = await fetch(`/api/bugs/${bugId}`, { method: 'PUT', headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+token}, body: JSON.stringify(payload) });
          if (!r.ok) {
            const txt = await r.text().catch(()=>r.statusText);
            return showNotif('Failed to save: '+txt);
          }
          showNotif('Saved');
          await loadBug();
        } catch(e) { console.error(e); showNotif('Save failed'); }
      }
    });
  } catch(e){}

  document.getElementById("logoutBtn").addEventListener("click", async ()=>{
    await fetch("/api/auth/logout", {method:"POST", headers: {"Authorization":"Bearer "+token}});
    localStorage.removeItem("tv_token");
    location.href = "/login";
  });

  loadBug();
})();
