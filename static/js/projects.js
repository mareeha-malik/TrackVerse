(function(){
  const token = localStorage.getItem("tv_token");
  if (!token) { location.href = "/login"; return; }

  function authHeaders() { return { "Authorization": "Bearer " + token, "Content-Type":"application/json" }; }

  async function fetchProjects() {
    const res = await fetch("/api/projects/", {headers: authHeaders()});
    const data = await res.json();
    const container = document.getElementById("projectsList");
    container.innerHTML = "";
    data.forEach(p => {
      const col = document.createElement("div");
      col.className = "col-md-6";
      col.innerHTML = `<div class="card p-3">
        <h5>${p.title}</h5>
        <p class="mb-1 text-muted">${p.owner || ""}</p>
        <div class="small text-muted">Bugs: ${p.bugs_total} Open: ${p.bugs_open}</div>
        <div class="mt-2"><a class="btn btn-sm btn-outline-primary" href="/projects/${p.id}">View</a> <button data-id="${p.id}" class="btn btn-sm btn-danger btn-delete">Delete</button></div>
      </div>`;
      container.appendChild(col);
    });
    document.querySelectorAll(".btn-delete").forEach(btn=>{
      btn.addEventListener("click", async (e)=>{
        if(!confirm("Delete project?")) return;
        const id = e.currentTarget.dataset.id;
        await fetch(`/api/projects/${id}`, {method:"DELETE", headers: authHeaders()});
        fetchProjects();
      });
    });
  }

  document.getElementById("projectForm").addEventListener("submit", async (e)=>{
    e.preventDefault();
    const payload = {
      title: document.getElementById("proj_title").value,
      description: document.getElementById("proj_desc").value,
      start_date: document.getElementById("proj_start").value || null,
      deadline: document.getElementById("proj_deadline").value || null,
      team_id: document.getElementById("proj_team") ? document.getElementById("proj_team").value || null : null
    };
    // include selected member ids when creating a team project
    const membersSel = document.getElementById('proj_members');
    if (membersSel && membersSel.options) {
      const selected = Array.from(membersSel.options).filter(o=>o.selected).map(o=>o.value);
      if (selected.length) payload.member_ids = selected;
    }
    const res = await fetch("/api/projects/", {method:"POST", headers: authHeaders(), body: JSON.stringify(payload)});
    if (res.ok) {
      document.getElementById("projectForm").reset();
      var modal = bootstrap.Modal.getInstance(document.getElementById("projectModal"));
      modal.hide();
      fetchProjects();
    } else {
      const j = await res.json();
      document.getElementById("flash").textContent = j.msg || "Error";
    }
  });

  // load user's teams into the project creation team dropdown
  async function loadTeams() {
    try {
      const res = await fetch('/api/teams', {headers: { 'Authorization': 'Bearer ' + token }});
      if (!res.ok) return;
      const payload = await res.json();
      const teams = Array.isArray(payload) ? payload : (payload.teams || payload);
      const sel = document.getElementById('proj_team');
      if (!sel) return;
      // preserve the default option already present in the template
      // clear any existing non-default options
      Array.from(sel.options).forEach(o => {
        if (o.value) sel.removeChild(o);
      });
      teams.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = t.name;
        sel.appendChild(opt);
      });
      // when team selection changes load the team members into the multi-select
      sel.addEventListener('change', async (ev) => {
        const tid = ev.target.value;
        const membersWrapper = document.getElementById('proj_members_wrapper');
        const membersSel = document.getElementById('proj_members');
        if (!tid) {
          // hide members selector
          if (membersWrapper) membersWrapper.style.display = 'none';
          // load only current user into assignee using /api/auth/profile
          try {
            const res = await fetch('/api/auth/profile', {headers: authHeaders()});
            const data = await res.json();
            const assign = document.getElementById('proj_assign');
            assign.innerHTML = '<option value="">Unassigned</option>';
            if (data && data.user) {
              const o = document.createElement('option'); o.value = data.user.id; o.textContent = data.user.name || data.user.email; assign.appendChild(o);
            }
          } catch (e) {}
          return;
        }
        try {
          const res = await fetch(`/api/teams/${tid}/members`, {headers: authHeaders()});
          if (!res.ok) throw new Error('failed');
          const data = await res.json();
          if (membersWrapper) membersWrapper.style.display = '';
          membersSel.innerHTML = '';
          const assign = document.getElementById('proj_assign');
          assign.innerHTML = '<option value="">Unassigned</option>';
          // support payload shape { members: [...] } or an array directly
          const list = Array.isArray(data) ? data : (data.members || data.users || []);
          list.forEach(m => {
            const o = document.createElement('option'); o.value = m.id; o.textContent = m.name; membersSel.appendChild(o);
            const ao = document.createElement('option'); ao.value = m.id; ao.textContent = m.name; assign.appendChild(ao);
          });
        } catch (e) {
          console.warn('failed to load team members', e);
        }
      });
    } catch (e) {
      console.warn('Failed to load teams', e);
    }
  }

  loadTeams();

  document.getElementById("logoutBtn").addEventListener("click", async ()=>{
    await fetch("/api/auth/logout", {method:"POST", headers: {"Authorization":"Bearer "+token}});
    localStorage.removeItem("tv_token");
    location.href = "/login";
  });

  // initial load
  fetchProjects();
})();
