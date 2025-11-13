(function(){
  const token = localStorage.getItem("tv_token");
  if (!token) { location.href = "/login"; return; }
  const projectId = window.TV_PROJECT_ID;
  function authHeaders() { return { "Authorization": "Bearer " + token, "Content-Type": "application/json" }; }

  async function loadOverview() {
    // backend exposes project detail at /api/bugs/projects/<id>
    const res = await fetch(`/api/bugs/projects/${projectId}`, {headers: authHeaders()});
    if (!res.ok) { document.getElementById("flash").textContent = "Unable to load project"; return; }
    const p = await res.json();
    document.getElementById("projectContainer").innerHTML = `<div class="card p-3">
      <h4>${p.title} <small class="text-muted">#${p.id}</small></h4>
      <div class="mb-2">${p.description || ""}</div>
      <div class="small text-muted">Status: ${p.status} · Start: ${p.start_date || "—"} · Deadline: ${p.deadline || "—"}</div>
    </div>`;
    const membersDiv = document.getElementById("membersList");
    membersDiv.innerHTML = (p.members || []).map(m=>`<div class="mb-1">#${m.id} <strong>${m.name}</strong> <span class="text-muted">${m.role}</span></div>`).join("") || "<div class='text-muted'>No members</div>";
  }

  document.getElementById("assignForm").addEventListener("submit", async (e)=>{
    e.preventDefault();
    const uid = document.getElementById("assign_user_id").value;
    const role = document.getElementById("assign_role").value;
    // use the bug-backed project PUT endpoint to set owner/member when available
    const res = await fetch(`/api/bugs/projects/${projectId}`, {method:"PUT", headers: authHeaders(), body: JSON.stringify({owner_id: Number(uid)})});
    if (res.ok) {
      document.getElementById("assign_user_id").value = "";
      showNotif("Member assigned successfully");
      loadOverview();
    } else {
      const j = await res.json();
      document.getElementById("flash").textContent = j.msg || "Error";
    }
  });

  // setup socket.io listener (pass token for server-side auth & room join)
  try {
  const socket = io({ transports: ["polling"], query: { token } });
    socket.on("connect", ()=> console.debug("socket connected"));
    socket.on("member_assigned", (data) => {
      if (data.project_id === projectId) {
        showNotif(`Member assigned: ${data.user_name} (${data.role})`);
        loadOverview();
      }
    });
    socket.on("bug_created", (data) => {
      if (data.project_id === projectId) {
        showNotif(`New bug created: ${data.title} (#${data.bug_id})`);
      }
    });
    socket.on("bug_assigned", (data) => {
      if (data.project_id === projectId) {
        showNotif(`Bug #${data.bug_id} assigned to ${data.assignee_name}`);
      }
    });
    socket.on("bug_resolved", (data) => {
      if (data.project_id === projectId) {
        showNotif(`Bug #${data.bug_id} marked ${data.status}`);
      }
    });
  } catch (e) {
    console.debug("socket init failed", e);
  }

  function showNotif(msg) {
    const box = document.getElementById("notifications");
    const el = document.createElement("div");
    el.className = "alert alert-info py-1";
    el.textContent = msg;
    box.prepend(el);
    setTimeout(()=> el.remove(), 8000);
  }

  document.getElementById("logoutBtn").addEventListener("click", async ()=>{
    await fetch("/api/auth/logout", {method:"POST", headers: {"Authorization":"Bearer "+token}});
    localStorage.removeItem("tv_token");
    location.href = "/login";
  });

  loadOverview();
})();
