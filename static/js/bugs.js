(function(){
  const token = localStorage.getItem("tv_token");
  if (!token) { location.href = "/login"; return; }
  function authHeaders() { return { "Authorization": "Bearer " + token }; }

  // new: socket connection for notifications and room joins
  let socket = null;
  try {
  socket = io({ transports: ["polling"], query: { token } });
    socket.on("connect", ()=> console.debug("bugs socket connected"));
    socket.on("bug_created", (data) => {
      showNotif(`New bug in project ${data.project_id}: ${data.title} (#${data.bug_id})`);
      loadBugs();
    });
    socket.on("bug_assigned", (data) => {
      showNotif(`Bug #${data.bug_id} assigned to ${data.assignee_name}`);
      loadBugs();
    });
    socket.on("bug_resolved", (data) => {
      showNotif(`Bug #${data.bug_id} marked ${data.status}`);
      loadBugs();
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

  async function loadProjectsDropdown() {
    const res = await fetch("/api/projects/", { headers: authHeaders() });
    const projects = await res.json();
    // cache projects for later (so we can infer team for a selected project)
    window.__projectsCache = projects || [];
    const sel = document.getElementById("filter_project");
    const sel2 = document.getElementById("bug_project");
    sel.innerHTML = '<option value="">All Projects</option>';
    sel2.innerHTML = '<option value="">Select project</option>';
    projects.forEach(p => {
      sel.innerHTML += `<option value="${p.id}">${p.title}</option>`;
      sel2.innerHTML += `<option value="${p.id}">${p.title}</option>`;
    });
    // when the project selection changes in the bug form, auto-set the team dropdown
    const bugProjectSel = document.getElementById('bug_project');
    const bugTeamSel = document.getElementById('bug_team');
    if (bugProjectSel && bugTeamSel) {
      bugProjectSel.addEventListener('change', (ev) => {
        const pid = ev.target.value ? parseInt(ev.target.value) : null;
        const proj = (window.__projectsCache || []).find(x => Number(x.id) === Number(pid));
        if (proj && proj.team_id) {
          bugTeamSel.value = proj.team_id;
        } else {
          bugTeamSel.value = '';
        }
        // refresh users dropdown to reflect team change
        loadUsersDropdown();
      });
    }
  }

  async function loadTeamsDropdown() {
    const sel = document.getElementById("bug_team");
    if (!sel) return;
    try {
      const res = await fetch("/api/teams/", { headers: authHeaders() });
      const data = await res.json();
      const teams = data.teams || [];
      sel.innerHTML = '<option value="">(No team)</option>';
      teams.forEach(t => {
        sel.innerHTML += `<option value="${t.id}">${t.name}</option>`;
      });
    } catch (err) {
      console.error("Failed to load teams", err);
      sel.innerHTML = '<option value="">(teams unavailable)</option>';
    }
  }

  async function loadBugs() {
    const q = document.getElementById("search_q").value;
    const params = new URLSearchParams();
    const proj = document.getElementById("filter_project").value;
    if (proj) params.set("project_id", proj);
    const status = document.getElementById("filter_status").value;
    if (status) params.set("status", status);
    const sev = document.getElementById("filter_severity").value;
    if (sev) params.set("severity", sev);
    if (q) params.set("q", q);
    const res = await fetch("/api/bugs/?" + params.toString(), {headers: authHeaders()});
    const data = await res.json();
    const tbody = document.getElementById("bugsTable");
    tbody.innerHTML = "";
    data.forEach(b => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${b.id}</td><td><a href="/bugs/${b.id}">${b.title}</a></td><td>${b.status}</td><td>${b.severity}</td><td>${b.assignee||""}</td><td><button data-id="${b.id}" class="btn btn-sm btn-danger btn-del">Delete</button></td>`;
      tbody.appendChild(tr);
    });
    document.querySelectorAll(".btn-del").forEach(btn=>{
      btn.addEventListener("click", async (e)=>{
        if(!confirm("Delete bug?")) return;
        const id = e.currentTarget.dataset.id;
        await fetch(`/api/bugs/${id}`, {method:"DELETE", headers: authHeaders()});
        loadBugs();
      });
    });
    // after populating table, join project rooms for visible bugs
    const projectIds = new Set();
    data.forEach(b => projectIds.add(String(b.project_id || "")));
    // emit join events for unique project ids
    if (socket) {
      projectIds.forEach(pid => {
        if (pid) socket.emit("join_project", { project_id: pid });
      });
    }
  }

  document.getElementById("applyFilters").addEventListener("click", ()=> loadBugs());

  

  document.getElementById("logoutBtn").addEventListener("click", async ()=>{
    await fetch("/api/auth/logout", {method:"POST", headers: {"Authorization":"Bearer "+token}});
    localStorage.removeItem("tv_token");
    location.href = "/login";
  });
async function loadUsersDropdown() {
  const sel = document.getElementById("bug_assignee");
  if (!sel) return;
  // if a team is selected, fetch team members endpoint; otherwise fallback to /api/users
  try {
    const teamSel = document.getElementById("bug_team");
    let members = [];
    if (teamSel && teamSel.value) {
      const res = await fetch(`/api/teams/${teamSel.value}/members`, { headers: authHeaders() });
      const data = await res.json();
      members = data.members || [];
    } else {
      // don't return the global user list when no team is selected; show only the current user
      const res = await fetch("/api/auth/profile", { headers: authHeaders() });
      const data = await res.json();
      members = data && data.user ? [data.user] : [];
    }
    sel.innerHTML = '<option value="">Select Assignee</option>';
    members.forEach(u => {
      sel.innerHTML += `<option value="${u.id}">${u.name || u.email}</option>`;
    });
  } catch (err) {
    console.error("Failed to load users/team members", err);
    sel.innerHTML = '<option value="">Error loading users</option>';
  }
}

  // init
// init
Promise.all([loadProjectsDropdown(), loadTeamsDropdown()]).then(()=>{
  // after teams are loaded, populate assignees and bugs
  loadUsersDropdown().then(loadBugs);
});

// when team selection changes, reload assignee dropdown
const teamSelect = document.getElementById("bug_team");
if (teamSelect) {
  teamSelect.addEventListener("change", async ()=>{
    await loadUsersDropdown();
  });
}

// ensure team_id included on submit
document.getElementById("bugForm").addEventListener("submit", async (e)=>{
  e.preventDefault();
  const form = document.getElementById("bugForm");
  const fd = new FormData();
  fd.append("title", document.getElementById("bug_title").value);
  fd.append("project_id", document.getElementById("bug_project").value);
  fd.append("description", document.getElementById("bug_desc").value);
  fd.append("severity", document.getElementById("bug_severity").value);
  fd.append("priority", document.getElementById("bug_priority").value);
  const teamVal = document.getElementById("bug_team").value;
  if (teamVal) fd.append("team_id", teamVal);
  const assignee = document.getElementById("bug_assignee").value;
  if (assignee) fd.append("assignee_id", assignee);
  const files = document.getElementById("bug_attachments").files;
  for (let i=0;i<files.length;i++) fd.append("attachments", files[i]);
  const res = await fetch("/api/bugs/", {method:"POST", headers: {"Authorization":"Bearer "+token}, body: fd});
  if (res.ok) {
    form.reset();
    var modal = bootstrap.Modal.getInstance(document.getElementById("bugModal"));
    modal.hide();
    loadBugs();
  } else {
    const j = await res.json();
    document.getElementById("flash").textContent = j.msg || "Error creating bug";
  }
});

// remove the duplicate submit handler below (original one exists earlier) - ensure we don't double-bind
})();
