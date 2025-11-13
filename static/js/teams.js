/* teams.js
   Provides simple team list/count and create/delete helpers used by the dashboard.
*/
(function(){
  const token = localStorage.getItem("tv_token");
  if (!token) { return; }
  function authHeaders(json=false) { return Object.assign({}, json ? { "Content-Type": "application/json" } : {}, { "Authorization": "Bearer " + token }); }

  async function fetchTeams() {
    try {
      const res = await fetch('/api/teams', { headers: authHeaders() });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn('fetchTeams failed', e);
      return null;
    }
  }

  // updateTeams is intentionally exposed globally so dashboard init can call it
  window.updateTeams = async function updateTeams() {
    const data = await fetchTeams();
    const countEl = document.getElementById('teamsCount');
    if (countEl) {
      const n = data && data.teams ? data.teams.length : 0;
      countEl.textContent = n;
    }
    // also render a simple list if provided
    const listEl = document.getElementById('teamsList');
    if (listEl) {
      listEl.innerHTML = '';
      const teams = (data && data.teams) || [];
      if (!teams.length) {
        listEl.innerHTML = '<div class="text-muted">No teams</div>';
        return;
      }
      teams.forEach(t => {
        const row = document.createElement('div');
        row.className = 'd-flex justify-content-between align-items-center py-2 border-bottom';
        row.innerHTML = `<div><strong>${escapeHtml(t.name)}</strong><div class="small text-muted">${t.description||''}</div></div>
                         <div class="btn-group btn-group-sm">
                           <a class="btn btn-sm btn-outline-primary" href="/teams/manage?team_id=${t.id}">Open</a>
                           <button data-id="${t.id}" class="btn btn-sm btn-danger btn-team-delete">Delete</button>
                         </div>`;
        listEl.appendChild(row);
      });
      // wire delete buttons
      listEl.querySelectorAll('.btn-team-delete').forEach(btn=>{
        btn.addEventListener('click', async (e)=>{
          if (!confirm('Delete team? This cannot be undone.')) return;
          const id = e.currentTarget.dataset.id;
          try {
            const res = await fetch(`/api/teams/${id}`, { method: 'DELETE', headers: authHeaders() });
            if (!res.ok) {
              const j = await res.json().catch(()=>({msg:'error'}));
              alert(j.msg || 'Failed to delete team');
              return;
            }
            updateTeams();
          } catch (err) {
            console.error('delete team failed', err);
            alert('Failed to delete team');
          }
        });
      });
    }
  };

  // handle team creation form
  const teamForm = document.getElementById('teamForm');
  if (teamForm) {
    teamForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const name = document.getElementById('team_name').value.trim();
      const description = document.getElementById('team_desc').value.trim();
      const invite_code = document.getElementById('team_invite').value.trim() || null;
      if (!name) return alert('Team name required');
      try {
        const res = await fetch('/api/teams', { method: 'POST', headers: authHeaders(true), body: JSON.stringify({ name, description, invite_code }) });
        const j = await res.json().catch(()=>({}));
        if (!res.ok) {
          alert(j.msg || 'Failed to create team');
          return;
        }
        // hide modal
        try {
          const modalEl = document.getElementById('teamModal');
          const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
          modal.hide();
        } catch (err) {}
        teamForm.reset();
        updateTeams();
      } catch (err) {
        console.error('create team failed', err);
        alert('Failed to create team');
      }
    });
  }

  // open modal button
  const openBtn = document.getElementById('openTeamModal');
  if (openBtn) {
    openBtn.addEventListener('click', ()=>{
      const el = document.getElementById('teamModal');
      const m = new bootstrap.Modal(el);
      m.show();
    });
  }

  // small helper
  function escapeHtml(s){ if(!s) return ''; return String(s).replace(/[&"'<>]/g, function(c){ return {'&':'&amp;','"':'&quot;',"'":"&#39;","<":"&lt;",">":"&gt;"}[c]; }); }

  // auto-refresh if a refresh button exists
  const refreshBtn = document.getElementById('refreshTeams');
  if (refreshBtn) refreshBtn.addEventListener('click', ()=> updateTeams());

  // initial run
  updateTeams();

})();
(function(){
  const token = localStorage.getItem("tv_token");
  if (!token) { location.href = "/login"; return; }
  function authHeaders() { return { "Authorization": "Bearer " + token, "Content-Type": "application/json" }; }

  const flash = (msg, type='info') => {
    const el = document.getElementById('flash');
    el.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
    setTimeout(()=> el.innerHTML = '', 5000);
  };

  async function loadTeams(){
    const out = document.getElementById('teamsList');
    out.innerHTML = 'Loading...';
    try{
      const res = await fetch('/api/teams/', { headers: authHeaders() });
      if (!res.ok) throw new Error('failed');
      const data = await res.json();
      const teams = data.teams || [];
      if (teams.length === 0) { out.innerHTML = '<div>No teams yet</div>'; return; }
      let html = '<div class="list-group">';
      for (const t of teams){
        html += `<div class="list-group-item bg-dark text-white d-flex justify-content-between align-items-start">
          <div>
            <div class="fw-bold">${t.name}</div>
            <div class="small text-muted">${t.description || ''} (id: ${t.id})</div>
          </div>
          <div>
            <button class="btn btn-sm btn-outline-light btn-members" data-id="${t.id}">Members</button>
          </div>
        </div>`;
      }
      html += '</div>';
      out.innerHTML = html;
      document.querySelectorAll('.btn-members').forEach(btn=> btn.addEventListener('click', async (e)=>{
        const id = e.currentTarget.dataset.id;
        await showMembers(id);
      }));
    }catch(err){
      out.innerHTML = '<div class="text-danger">Error loading teams</div>';
      console.error(err);
    }
  }

  async function showMembers(teamId){
    try{
      // fetch members and team detail (to see if current user is creator and get invite code)
      const [membersRes, detailRes] = await Promise.all([
        fetch(`/api/teams/${teamId}/members`, { headers: authHeaders() }),
        fetch(`/api/teams/${teamId}`, { headers: authHeaders() })
      ]);
      if (!membersRes.ok) throw new Error('fetch members failed');
      if (!detailRes.ok) throw new Error('fetch team detail failed');
      const membersData = await membersRes.json();
      const teamData = await detailRes.json();
      const members = membersData.members || [];

      // build modal content
      const modalTitle = document.getElementById('membersModalTitle');
      const modalBody = document.getElementById('membersModalBody');
      modalTitle.textContent = `Members — ${teamData.name || ('Team '+teamId)}`;
      let html = '';
      html += `<div class="mb-2"><strong>Team ID:</strong> ${teamData.id}</div>`;
      if (teamData.invite_code) {
        html += `<div class="mb-2"><strong>Invite code:</strong> <code id="inviteCode">${teamData.invite_code}</code> <button id="regenInvite" class="btn btn-sm btn-outline-light">Regenerate</button> <button id="copyInvite" class="btn btn-sm btn-outline-light">Copy</button></div>`;
      }
      html += '<ul class="list-group">';
      for (const m of members) {
        html += `<li class="list-group-item bg-dark text-white d-flex justify-content-between align-items-center">${m.name || m.email} <small class="text-muted">(${m.email})</small><div><button class="btn btn-sm btn-outline-danger btn-remove" data-uid="${m.id}">Remove</button></div></li>`;
      }
      html += '</ul>';
      modalBody.innerHTML = html;

      // show modal
      const membersModalEl = document.getElementById('membersModal');
      const membersModal = new bootstrap.Modal(membersModalEl);
      membersModal.show();

      // bind copy button
      const copyBtn = document.getElementById('copyInvite');
      if (copyBtn) copyBtn.addEventListener('click', ()=> navigator.clipboard.writeText(teamData.invite_code));

      // bind regenerate (only shown when invite_code exists, which indicates current user is creator)
      const regenBtn = document.getElementById('regenInvite');
      if (regenBtn) regenBtn.addEventListener('click', async ()=>{
        regenBtn.disabled = true;
        try{
          const r = await fetch(`/api/teams/${teamId}/invite/regenerate`, { method: 'POST', headers: authHeaders() });
          const j = await r.json();
          if (!r.ok) { flash(j.msg || 'Failed to regenerate', 'danger'); regenBtn.disabled = false; return; }
          document.getElementById('inviteCode').textContent = j.invite_code;
          flash('Invite regenerated', 'success');
          await loadTeams();
        }catch(err){ console.error(err); flash('Error regenerating invite', 'danger'); }
        regenBtn.disabled = false;
      });

      // bind remove buttons
      modalBody.querySelectorAll('.btn-remove').forEach(btn=> btn.addEventListener('click', async (e)=>{
        const uid = e.currentTarget.dataset.uid;
        if (!confirm('Remove this member?')) return;
        try{
          const r = await fetch(`/api/teams/${teamId}/members/${uid}`, { method: 'DELETE', headers: authHeaders() });
          const j = await r.json();
          if (!r.ok) { flash(j.msg || 'Failed to remove', 'danger'); return; }
          flash('Member removed', 'success');
          // refresh modal content and teams list
          await showMembers(teamId);
          await loadTeams();
        }catch(err){ console.error(err); flash('Error removing member', 'danger'); }
      }));

    }catch(err){
      console.error(err);
      flash('Failed to load members', 'danger');
    }
  }

  document.getElementById('createTeamForm').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const name = document.getElementById('team_name').value.trim();
    const description = document.getElementById('team_description').value.trim();
    const invite = document.getElementById('team_invite').value.trim();
    if (!name) { flash('Name required', 'warning'); return; }
    const payload = { name, description };
    if (invite) payload.invite_code = invite;
    try{
      const res = await fetch('/api/teams/', { method: 'POST', headers: authHeaders(), body: JSON.stringify(payload) });
      const j = await res.json();
      if (!res.ok) { flash(j.msg || 'Failed to create', 'danger'); return; }
      flash('Team created', 'success');
      if (j.invite_code) document.getElementById('createdInvite').innerHTML = `<div class="small">Invite code: <strong>${j.invite_code}</strong> <button class="btn btn-sm btn-outline-light" id="copyInvite">Copy</button></div>`;
      document.getElementById('copyInvite')?.addEventListener('click', ()=> navigator.clipboard.writeText(j.invite_code));
      document.getElementById('createTeamForm').reset();
      await loadTeams();
    }catch(err){ console.error(err); flash('Error creating team', 'danger'); }
  });

  document.getElementById('joinTeamForm').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const code = document.getElementById('join_code').value.trim();
    if (!code) { flash('Invite code or team id required', 'warning'); return; }
    const payload = {};
    if (/^\d+$/.test(code)) payload.team_id = parseInt(code,10); else payload.invite_code = code;
    try{
      const res = await fetch('/api/teams/join', { method: 'POST', headers: authHeaders(), body: JSON.stringify(payload) });
      const j = await res.json();
      if (!res.ok) { flash(j.msg || 'Join failed', 'danger'); return; }
      flash(j.msg || 'Joined', 'success');
      document.getElementById('joinTeamForm').reset();
      await loadTeams();
    }catch(err){ console.error(err); flash('Error joining team', 'danger'); }
  });

  document.getElementById('refreshBtn').addEventListener('click', loadTeams);
  document.getElementById('logoutBtn').addEventListener('click', async ()=>{
    await fetch('/api/auth/logout', { method: 'POST', headers: { 'Authorization': 'Bearer '+token } });
    localStorage.removeItem('tv_token'); location.href = '/login';
  });

  // init
  loadTeams();

  // If an invite code or team id is present in the URL, prefill the join form and focus it.
  try {
    const params = new URLSearchParams(window.location.search);
    const inviteParam = params.get('invite') || params.get('invite_code') || params.get('code') || params.get('inviteCode');
    const auto = params.get('auto');
    if (inviteParam) {
      const joinInput = document.getElementById('join_code');
      if (joinInput) {
        joinInput.value = inviteParam;
        joinInput.focus();

        // If auto=1, show confirmation modal and auto-submit when confirmed.
        if (auto === '1') {
          const autoModalEl = document.getElementById('autoJoinModal');
          const autoModal = new bootstrap.Modal(autoModalEl);
          autoModal.show();

          const confirmBtn = document.getElementById('autoJoinConfirm');
          const cancelBtn = document.getElementById('autoJoinCancel');

          const cleanup = () => {
            confirmBtn?.removeEventListener('click', onConfirm);
            cancelBtn?.removeEventListener('click', onCancel);
          };

          const onConfirm = async () => {
            cleanup();
            autoModal.hide();
            // submit the join form programmatically
            const payload = {};
            if (/^\d+$/.test(joinInput.value.trim())) payload.team_id = parseInt(joinInput.value.trim(), 10);
            else payload.invite_code = joinInput.value.trim();
            try {
              const res = await fetch('/api/teams/join', { method: 'POST', headers: authHeaders(), body: JSON.stringify(payload) });
              const j = await res.json();
              if (!res.ok) { flash(j.msg || 'Join failed', 'danger'); return; }
              flash(j.msg || 'Joined', 'success');
              await loadTeams();
            } catch (err) { console.error(err); flash('Error joining team', 'danger'); }
          };

          const onCancel = () => { cleanup(); };

          confirmBtn?.addEventListener('click', onConfirm);
          cancelBtn?.addEventListener('click', onCancel);
        }
      }
    }
  } catch (e) {
    // ignore
  }
})();
