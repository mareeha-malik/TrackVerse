(function(){
  const token = localStorage.getItem('tv_token');
  if (!token) { location.href = '/login'; return; }
  const headers = { 'Authorization': 'Bearer '+token, 'Content-Type': 'application/json' };
  const params = new URLSearchParams(location.search);
  const teamId = params.get('team_id');
  if (!teamId) { document.getElementById('flash').innerHTML = '<div class="alert alert-warning">Open this page with ?team_id=ID</div>'; return; }

  function flash(msg, cls='info') { document.getElementById('flash').innerHTML = `<div class="alert alert-${cls}">${msg}</div>`; setTimeout(()=> document.getElementById('flash').innerHTML='',4000); }

  async function loadInvites(){
    const el = document.getElementById('invitesList'); el.innerHTML = 'Loading...';
    try{
      const res = await fetch(`/api/teams/${teamId}/invites`, { headers });
      if (!res.ok) throw new Error('failed');
      const j = await res.json();
      const invs = j.invites || [];
      if (invs.length===0) { el.innerHTML = '<div>No invites</div>'; return; }
      let html = '<ul class="list-group">';
      invs.forEach(i=> html += `<li class="list-group-item d-flex justify-content-between align-items-center bg-dark text-white">${i.invited_email||'(any)'} <small class="text-muted">${i.invite_code} ${i.expires_at?('expires:'+i.expires_at):''}</small><div><button class="btn btn-sm btn-outline-danger btn-revoke" data-id="${i.id}">Revoke</button></div></li>`);
      html += '</ul>';
      el.innerHTML = html;
      el.querySelectorAll('.btn-revoke').forEach(b=> b.addEventListener('click', async (e)=>{
        const id = e.currentTarget.dataset.id;
        if (!confirm('Revoke invite?')) return;
        const r = await fetch(`/api/teams/${teamId}/invites/${id}`, { method: 'DELETE', headers });
        const j = await r.json(); if (!r.ok) { flash(j.msg||'Failed','danger'); return; }
        flash('Revoked','success'); loadInvites();
      }));
    }catch(err){ console.error(err); el.innerHTML = '<div class="text-danger">Error</div>'; }
  }

  document.getElementById('inviteForm').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const email = document.getElementById('invite_email').value.trim();
    const expires = document.getElementById('invite_expires').value.trim();
    const payload = {};
    if (email) payload.email = email; if (expires) payload.expires_in_hours = expires;
    const res = await fetch(`/api/teams/${teamId}/invite`, { method: 'POST', headers, body: JSON.stringify(payload) });
    const j = await res.json(); if (!res.ok) { flash(j.msg||'Failed','danger'); return; }
    flash('Invite created: '+j.invite_code,'success'); document.getElementById('inviteForm').reset(); loadInvites();
  });

  // members
  let currentPage = 1, perPage = 10;
  async function loadMembers(page=1){
    const el = document.getElementById('membersTable'); el.innerHTML = 'Loading...';
    try{
      const res = await fetch(`/api/teams/${teamId}/members?page=${page}&per_page=${perPage}`, { headers });
      if (!res.ok) throw new Error('failed');
      const j = await res.json();
      const members = j.members || [];
      if (members.length===0) { el.innerHTML = '<div>No members</div>'; return; }
      let html = '<table class="table table-dark table-striped"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Action</th></tr></thead><tbody>';
      for (const m of members) {
        html += `<tr><td>${m.name}</td><td>${m.email}</td><td><select class="form-select form-select-sm role-select" data-uid="${m.id}"><option value="owner" ${m.role==='owner'?'selected':''}>owner</option><option value="maintainer" ${m.role==='maintainer'?'selected':''}>maintainer</option><option value="member" ${m.role==='member'?'selected':''}>member</option></select></td><td><button class="btn btn-sm btn-danger btn-remove" data-uid="${m.id}">Remove</button></td></tr>`;
      }
      html += '</tbody></table>';
      el.innerHTML = html;
      // bind role selects
      document.querySelectorAll('.role-select').forEach(s=> s.addEventListener('change', async (e)=>{
        const uid = e.currentTarget.dataset.uid; const role = e.currentTarget.value;
        const r = await fetch(`/api/teams/${teamId}/members/${uid}/role`, { method: 'POST', headers, body: JSON.stringify({ role }) });
        const j = await r.json(); if (!r.ok) { flash(j.msg||'Failed','danger'); return; }
        flash('Role updated','success');
      }));
      // bind remove
      document.querySelectorAll('.btn-remove').forEach(b=> b.addEventListener('click', async (e)=>{
        const uid = e.currentTarget.dataset.uid; if (!confirm('Remove member?')) return;
        const r = await fetch(`/api/teams/${teamId}/members/${uid}`, { method: 'DELETE', headers }); const j = await r.json(); if (!r.ok) { flash(j.msg||'Failed','danger'); return; }
        flash('Removed','success'); loadMembers(currentPage); loadInvites();
      }));
      // paging
      const total = j.total || 0; const pages = Math.max(1, Math.ceil(total/perPage));
      const paging = document.getElementById('membersPaging'); paging.innerHTML = '';
      for (let i=1;i<=pages;i++){ paging.innerHTML += `<li class="page-item ${i===page?'active':''}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`; }
      paging.querySelectorAll('a').forEach(a=> a.addEventListener('click', (ev)=>{ ev.preventDefault(); const p = parseInt(ev.currentTarget.dataset.page); currentPage = p; loadMembers(p); }));
    }catch(err){ console.error(err); el.innerHTML = '<div class="text-danger">Error loading members</div>'; }
  }

  document.getElementById('logoutBtn').addEventListener('click', async ()=>{ await fetch('/api/auth/logout',{method:'POST', headers:{ Authorization: 'Bearer '+token }}); localStorage.removeItem('tv_token'); location.href='/login'; });

  loadInvites(); loadMembers(currentPage);
})();
