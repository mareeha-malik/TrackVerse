from flask import Blueprint, request, jsonify, send_from_directory, current_app
from extensions import db, socketio
from models import Bug, Project, User, Comment, Attachment, Activity, BugStatus, BugPriority, SeverityEnum, Team
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils import allowed_file, save_upload, auto_create_syntax_bugs, send_email
from datetime import datetime
import os
from models import RoleEnum

bug_bp = Blueprint("bugs", __name__)

# --- NEW helper: robustly resolve current user from JWT identity ---
def current_user():
    """Return User or None. Accepts either an int identity or a dict containing 'id'."""
    ident = get_jwt_identity()
    if ident is None:
        return None
    uid = None
    if isinstance(ident, dict):
        # common shapes
        uid = ident.get("id") or ident.get("user_id") or ident.get("uid")
    else:
        uid = ident
    try:
        uid = int(uid)
    except Exception:
        return None
    return db.session.get(User, uid)


def _accessible_project_ids(user):
    """Return a set of project ids the user may access: personal projects (owner) and projects belonging to user's teams.
    Admins bypass and get all project ids (empty set indicates all in this helper's usage).
    """
    if not user:
        return set()
    # admins see everything
    if getattr(user, 'role', None) == RoleEnum.ADMIN:
        return None
    # collect team ids from both the legacy user.teams relationship and the TeamMember records
    team_ids = []
    try:
        team_ids = [t.id for t in (user.teams or []) if getattr(t, 'id', None) is not None]
    except Exception:
        team_ids = []
    try:
        from models import TeamMember
        tm_rows = TeamMember.query.filter_by(user_id=user.id).with_entities(TeamMember.team_id).all()
        for r in (tm_rows or []):
            if isinstance(r, (list, tuple)):
                tid = r[0]
            else:
                tid = getattr(r, 'team_id', None) if hasattr(r, 'team_id') else r
            if tid and tid not in team_ids:
                team_ids.append(tid)
    except Exception:
        pass
    q = Project.query
    from sqlalchemy import or_
    # only use Project.team_id if the column exists in the model/table metadata
    has_team_col = False
    try:
        has_team_col = 'team_id' in Project.__table__.columns.keys()
    except Exception:
        has_team_col = hasattr(Project, 'team_id')
    if team_ids and has_team_col:
        q = q.filter(or_(Project.owner_id == user.id, Project.team_id.in_(team_ids)))
    else:
        q = q.filter(Project.owner_id == user.id)
    return set([p.id for p in q.with_entities(Project.id).all()])

@bug_bp.route("/", methods=["POST"])
@jwt_required()
def create_bug():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401

    # allow multipart/form-data for attachments
    if request.content_type and "multipart/form-data" in request.content_type:
        data = request.form or {}
    else:
        data = request.json or {}
    title = data.get("title")
    project_id = data.get("project_id")
    if not title or not project_id:
        return jsonify({"msg":"title and project_id required"}), 400
    try:
        project_id = int(project_id)
    except Exception:
        return jsonify({"msg":"invalid project_id"}), 400
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"msg":"project not found"}), 404

    severity = data.get("severity", SeverityEnum.MAJOR)
    priority = data.get("priority", BugPriority.MEDIUM)
    b = Bug(title=title, description=data.get("description"), priority=priority,
            project_id=project_id, reporter=user, severity=severity)
    # optional team selection
    team_id = data.get("team_id")
    team = None
    if team_id:
        try:
            team = db.session.get(Team, int(team_id))
            if team:
                b.team = team
        except Exception:
            team = None

    assignee_id = data.get("assignee_id")
    if assignee_id:
        try:
            aid = int(assignee_id)
            assignee = db.session.get(User, aid)
            # validation: if a team is selected, assignee must be a member
            if team:
                if assignee not in team.members:
                    return jsonify({"msg": "assignee must be a member of the selected team"}), 400
            else:
                # if either reporter or assignee belong to teams, require a shared team
                reporter_teams = set([t.id for t in (user.teams or [])])
                assignee_teams = set([t.id for t in (assignee.teams or [])])
                if (reporter_teams or assignee_teams) and reporter_teams.intersection(assignee_teams) == set():
                    return jsonify({"msg": "assignee must share a team with reporter"}), 400
            b.assignee_id = aid
        except Exception:
            # ignore bad assignee id
            pass
    db.session.add(b)
    db.session.commit()
    # attachments (multipart)
    for f in request.files.getlist("attachments"):
        if f and allowed_file(f.filename):
            filename, path = save_upload(f)
            att = Attachment(bug=b, filename=filename, filepath=path)
            db.session.add(att)
            db.session.commit()
            # if .py file, trigger syntax scan and auto-create bug(s)
            if filename.lower().endswith(".py"):
                created = auto_create_syntax_bugs(project_id=project_id, reporter=user, filename=filename, filepath=path)
                if created:
                    # record activity for each auto-created bug
                    for c in created:
                        act = Activity(actor_id=None, verb="auto-created syntax bug", target_type="bug", target_id=c["bug_id"])
                        db.session.add(act)
    db.session.commit()
    # emit new bug event to project room
    try:
        socketio.emit("bug_created", {"bug_id": b.id, "title": b.title, "project_id": project_id}, room=f"project_{project_id}")
    except Exception:
        pass
    act = Activity(actor_id=user.id, verb="created bug", target_type="bug", target_id=b.id)
    db.session.add(act); db.session.commit()
    return jsonify({"id": b.id}), 201

@bug_bp.route("/<int:bug_id>", methods=["GET","PUT","DELETE"])
@jwt_required()
def bug_detail(bug_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    b = db.session.get(Bug, bug_id)
    if not b:
        return jsonify({"msg":"not found"}), 404
    if request.method == "GET":
        return jsonify({
            "id":b.id,"title":b.title,"description":b.description,"severity":b.severity,"priority":b.priority,
            "status":b.status,"project_id":b.project_id,"assignee_id":b.assignee_id,
            "attachments":[{"id":a.id,"filename":a.filename} for a in b.attachments],
            "comments":[{"id":c.id,"body":c.body,"user":c.user.name,"created_at":c.created_at.isoformat()} for c in b.comments],
            "created_at": b.created_at.isoformat(), "updated_at": b.updated_at.isoformat()
        })
    elif request.method == "PUT":
        data = request.json or {}
        old_status = b.status
        old_assignee = b.assignee_id
        b.title = data.get("title", b.title)
        b.description = data.get("description", b.description)
        b.severity = data.get("severity", b.severity)
        b.priority = data.get("priority", b.priority)
        b.status = data.get("status", b.status)
        # normalize assignee id if provided and validate
        if "assignee_id" in data:
            try:
                new_aid = int(data.get("assignee_id"))
                new_assignee = db.session.get(User, new_aid)
                # determine relevant team: prefer bug.team, else require shared team with actor
                if b.team_id:
                    t = db.session.get(Team, b.team_id)
                    if new_assignee not in (t.members or []):
                        return jsonify({"msg":"assignee must be a member of the bug's team"}), 400
                else:
                    actor_teams = set([t.id for t in (user.teams or [])])
                    assignee_teams = set([t.id for t in (new_assignee.teams or [])])
                    if (actor_teams or assignee_teams) and actor_teams.intersection(assignee_teams) == set():
                        return jsonify({"msg":"assignee must share a team with you"}), 400
                b.assignee_id = new_aid
            except Exception:
                # ignore invalid assignee id (or return 400)
                pass
        db.session.commit()
        # notifications
        if old_assignee != b.assignee_id and b.assignee:
            try:
                send_email(b.assignee.email, "Bug assigned", f"You have been assigned bug #{b.id}: {b.title}")
            except Exception:
                pass
            act = Activity(actor_id=user.id, verb=f"assigned bug to {b.assignee.name}", target_type="bug", target_id=b.id)
            db.session.add(act)
            # emit assignment event to project and to the assignee user room
            try:
                socketio.emit("bug_assigned", {"bug_id": b.id, "assignee_id": b.assignee_id, "assignee_name": b.assignee.name, "project_id": b.project_id}, room=f"project_{b.project_id}")
                socketio.emit("bug_assigned", {"bug_id": b.id, "assignee_id": b.assignee_id, "assignee_name": b.assignee.name, "project_id": b.project_id}, room=f"user_{b.assignee_id}")
            except Exception:
                pass

        if old_status != b.status:
            if b.status.lower() in ("resolved", "closed"):
                # notify reporter
                try:
                    if b.reporter and b.reporter.email:
                        send_email(b.reporter.email, "Bug status changed", f"Bug #{b.id} is now {b.status}")
                except Exception:
                    pass
                # emit resolved event to project and reporter
                try:
                    socketio.emit("bug_resolved", {"bug_id": b.id, "status": b.status, "project_id": b.project_id}, room=f"project_{b.project_id}")
                    if b.reporter_id:
                        socketio.emit("bug_resolved", {"bug_id": b.id, "status": b.status, "project_id": b.project_id}, room=f"user_{b.reporter_id}")
                except Exception:
                    pass
            act = Activity(actor_id=user.id, verb=f"changed bug status to {b.status}", target_type="bug", target_id=b.id)
            db.session.add(act)
        db.session.commit()
        return jsonify({"msg":"updated"})
    else:
        db.session.delete(b)
        db.session.commit()
        act = Activity(actor_id=user.id, verb="deleted bug", target_type="bug", target_id=bug_id)
        db.session.add(act); db.session.commit()
        return jsonify({"msg":"deleted"})

@bug_bp.route("/<int:bug_id>/comment", methods=["POST"])
@jwt_required()
def add_comment(bug_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    b = db.session.get(Bug, bug_id)
    if not b:
        return jsonify({"msg":"not found"}), 404
    data = request.json or {}
    body = data.get("body")
    if not body:
        return jsonify({"msg":"body required"}), 400
    c = Comment(bug=b, user=user, body=body)
    db.session.add(c)
    act = Activity(actor_id=user.id, verb="commented on bug", target_type="bug", target_id=b.id)
    db.session.add(act)
    db.session.commit()
    return jsonify({"id": c.id}), 201

@bug_bp.route("/<int:bug_id>/attachments/<int:att_id>", methods=["GET"])
@jwt_required()
def get_attachment(bug_id, att_id):
    a = db.session.get(Attachment, att_id)
    if not a:
        return jsonify({"msg":"not found"}), 404
    if a.bug_id != bug_id:
        return jsonify({"msg":"not found"}), 404
    folder = current_app.config['UPLOAD_FOLDER']
    return send_from_directory(folder, a.filename, as_attachment=True)

@bug_bp.route("/", methods=["GET"])
@jwt_required()
def list_bugs():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    args = request.args
    q = Bug.query
    project_id = args.get("project_id")
    status = args.get("status")
    priority = args.get("priority")
    severity = args.get("severity")
    assignee = args.get("assignee_id")
    search = args.get("q")
    # normalize project_id query param
    if project_id:
        try:
            project_id = int(project_id)
            # enforce access: only allow querying a project the user can access
            acc = _accessible_project_ids(user)
            if acc is not None and project_id not in acc:
                return jsonify([])
            q = q.filter_by(project_id=project_id)
        except Exception:
            # ignore bad project_id and don't filter
            pass
    else:
        # if no project specified, restrict bugs to projects the user can access
        acc = _accessible_project_ids(user)
        if acc is not None:
            if not acc:
                # user has no accessible projects -> empty list
                return jsonify([])
            q = q.filter(Bug.project_id.in_(list(acc)))
    if status: q = q.filter_by(status=status)
    if priority: q = q.filter_by(priority=priority)
    if severity: q = q.filter_by(severity=severity)
    if assignee:
        try:
            assignee = int(assignee)
            q = q.filter_by(assignee_id=assignee)
        except Exception:
            q = q.filter_by(assignee_id=assignee)
    if search:
        q = q.filter((Bug.title.ilike(f"%{search}%")) | (Bug.description.ilike(f"%{search}%")))
    bugs = q.order_by(Bug.created_at.desc()).all()
    out = []
    for b in bugs:
        out.append({"id":b.id,"title":b.title,"status":b.status,"priority":b.priority,"severity": b.severity,"assignee": b.assignee.name if b.assignee else None, "project_id": b.project_id})
    return jsonify(out)

@bug_bp.route("/analytics/summary", methods=["GET"])
@jwt_required()
def analytics_summary():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    total_users = User.query.count()
    # compute global counts to decide whether to show demo data
    global_total_bugs = Bug.query.count()
    global_total_projects = Project.query.count()
    acc = _accessible_project_ids(user)
    # admins see all and may receive demo data if the DB is empty
    if acc is None:
        from sqlalchemy import func
        total_bugs = global_total_bugs
        open_bugs = Bug.query.filter_by(status="Open").count()
        total_projects = global_total_projects
        status_counts = db.session.query(Bug.status, func.count(Bug.id)).group_by(Bug.status).all()
        priority_counts = db.session.query(Bug.priority, func.count(Bug.id)).group_by(Bug.priority).all()
        severity_counts = db.session.query(Bug.severity, func.count(Bug.id)).group_by(Bug.severity).all()
        recent = Bug.query.order_by(Bug.created_at.desc()).limit(10).all()
        show_demo = (global_total_bugs == 0 and global_total_projects == 0)
    else:
        from sqlalchemy import func
        # non-admin: compute counts only for accessible projects
        if not acc:
            total_bugs = 0
            open_bugs = 0
            total_projects = 0
            status_counts = []
            priority_counts = []
            severity_counts = []
            recent = []
        else:
            total_bugs = db.session.query(func.count(Bug.id)).filter(Bug.project_id.in_(list(acc))).scalar() or 0
            open_bugs = db.session.query(func.count(Bug.id)).filter(Bug.project_id.in_(list(acc))).filter(Bug.status == "Open").scalar() or 0
            total_projects = db.session.query(func.count(Project.id)).filter(Project.id.in_(list(acc))).scalar() or 0
            status_counts = db.session.query(Bug.status, func.count(Bug.id)).filter(Bug.project_id.in_(list(acc))).group_by(Bug.status).all()
            priority_counts = db.session.query(Bug.priority, func.count(Bug.id)).filter(Bug.project_id.in_(list(acc))).group_by(Bug.priority).all()
            severity_counts = db.session.query(Bug.severity, func.count(Bug.id)).filter(Bug.project_id.in_(list(acc))).group_by(Bug.severity).all()
            recent = Bug.query.filter(Bug.project_id.in_(list(acc))).order_by(Bug.created_at.desc()).limit(10).all()
        # do not show demo data to non-admins even if totals are zero
        show_demo = False
    recent_out = [{"id":r.id,"title":r.title,"status":r.status,"created_at":r.created_at.isoformat()} for r in recent]

    # If there is no real data and the global DB is empty, return friendly demo data only for admins.
    if show_demo:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        demo_recent = []
        # small set of demo recent bugs (no DB writes)
        demo_recent.append({"id": None, "title": "Demo: Fix login error", "status": "Open", "created_at": (now - timedelta(days=1)).isoformat()})
        demo_recent.append({"id": None, "title": "Demo: Improve dashboard", "status": "In Progress", "created_at": (now - timedelta(days=2)).isoformat()})
        demo_status = {"Open": 3, "In Progress": 1, "Resolved": 1}
        demo_priority = {"High": 2, "Medium": 2, "Low": 1}
        demo_severity = {"Critical": 1, "Major": 2, "Minor": 2}
        return jsonify({
            "demo": True,
            "total_bugs": 5,
            "open_bugs": 3,
            "total_projects": 2,
            "total_users": total_users,
            "by_status": demo_status,
            "by_priority": demo_priority,
            "by_severity": demo_severity,
            "recent": demo_recent
        })

    return jsonify({
        "demo": False,
        "total_bugs": total_bugs,
        "open_bugs": open_bugs,
        "total_projects": total_projects,
        "total_users": total_users,
        "by_status": dict(status_counts),
        "by_priority": dict(priority_counts),
        "by_severity": dict(severity_counts),
        "recent": recent_out
    })

# --- new: simple project endpoints (create/list/get) ---
@bug_bp.route("/projects", methods=["POST", "GET"])
@jwt_required()
def projects():
    user = current_user()
    if not user:
        return jsonify({"msg": "unauthorized"}), 401

    if request.method == "POST":
        data = request.json or {}
        title = data.get("title") or data.get("name")
        description = data.get("description", "")
        if not title:
            return jsonify({"msg": "title required"}), 400
        # try common Project fields (name/title + owner_id)
        try:
            # prefer `name`, fallback to `title` if model uses that
            if hasattr(Project, "name"):
                p = Project(name=title, description=description)
            else:
                p = Project(title=title, description=description)
            # attach owner_id when possible
            if hasattr(p, "owner_id"):
                try:
                    p.owner_id = int(user.id)
                except Exception:
                    pass
            # optional: allow associating a project with a team if provided and user is a member
            team_id = data.get("team_id")
            if team_id and hasattr(p, "team_id"):
                try:
                    tid = int(team_id)
                    t = db.session.get(Team, tid)
                    if t and user in (t.members or []):
                        p.team_id = tid
                except Exception:
                    pass
            db.session.add(p)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"msg": "failed to create project", "error": str(e)}), 500
        return jsonify({"id": p.id}), 201

    # GET: list projects (only projects current user may access)
    acc = _accessible_project_ids(user)
    if acc is None:
        ps = Project.query.order_by(Project.id.desc()).all()
    else:
        if not acc:
            ps = []
        else:
            ps = Project.query.filter(Project.id.in_(list(acc))).order_by(Project.id.desc()).all()
    out = []
    for p in ps:
        out.append({
            "id": getattr(p, "id", None),
            "name": getattr(p, "name", getattr(p, "title", None)),
            "description": getattr(p, "description", None),
            "owner_id": getattr(p, "owner_id", getattr(p, "owner", None))
        })
    return jsonify(out)

@bug_bp.route("/projects/<int:project_id>", methods=["GET", "PUT", "DELETE"])
@jwt_required()
def project_detail(project_id):
    user = current_user()
    if not user:
        return jsonify({"msg": "unauthorized"}), 401

    p = Project.query.get_or_404(project_id)
    # enforce access: only allow viewing/modifying projects the user can access
    acc = _accessible_project_ids(user)
    if acc is not None and project_id not in acc:
        return jsonify({"msg":"not found"}), 404

    if request.method == "GET":
        return jsonify({
            "id": p.id,
            "name": getattr(p, "name", getattr(p, "title", None)),
            "description": getattr(p, "description", None)
        })

    if request.method == "PUT":
        data = request.json or {}
        title = data.get("title") or data.get("name")
        description = data.get("description")
        updated = False
        try:
            if title is not None:
                if hasattr(p, "name"):
                    p.name = title
                else:
                    p.title = title
                updated = True
            if description is not None and hasattr(p, "description"):
                p.description = description
                updated = True
            # optional owner change
            if "owner_id" in data and hasattr(p, "owner_id"):
                try:
                    p.owner_id = int(data.get("owner_id"))
                    updated = True
                except Exception:
                    pass
            if updated:
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"msg":"failed to update project", "error": str(e)}), 500
        return jsonify({
            "id": p.id,
            "name": getattr(p, "name", getattr(p, "title", None)),
            "description": getattr(p, "description", None)
        })

    # DELETE
    try:
        db.session.delete(p)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg":"failed to delete project", "error": str(e)}), 500
    return jsonify({"msg":"deleted"}), 200
