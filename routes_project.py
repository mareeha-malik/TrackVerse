from flask import Blueprint, request, jsonify
from extensions import db, socketio
from models import Project, User, ProjectMember, Activity, Bug, RoleEnum, Team, TeamMember
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import or_



def current_user():
    ident = get_jwt_identity()
    if ident is None:
        return None
    try:
        uid = int(ident)
    except Exception:
        # allow dict-like identity shapes
        if isinstance(ident, dict):
            uid = ident.get("id") or ident.get("user_id") or ident.get("uid")
        else:
            return None
    try:
        return db.session.get(User, int(uid))
    except Exception:
        return None


def _accessible_project_ids(user):
    if not user:
        return set()
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
        # with_entities may return scalar rows or single-item tuples depending on SQLAlchemy version;
        # handle both shapes robustly
        tm_rows = TeamMember.query.filter_by(user_id=user.id).with_entities(TeamMember.team_id).all()
        tm_ids = []
        for r in (tm_rows or []):
            if isinstance(r, (list, tuple)):
                tid = r[0]
            else:
                # row object with attribute (older SQLAlchemy) or scalar
                tid = getattr(r, 'team_id', None) if hasattr(r, 'team_id') else r
            if tid and tid not in team_ids:
                team_ids.append(tid)
    except Exception:
        pass
    q = Project.query
    if team_ids:
        q = q.filter(or_(Project.owner_id == user.id, Project.team_id.in_(team_ids)))
    else:
        q = q.filter(Project.owner_id == user.id)
    return set([p.id for p in q.with_entities(Project.id).all()])

project_bp = Blueprint("projects", __name__)

# ---------------------------
# ✅ GET all projects
# ---------------------------
@project_bp.route("/", methods=["GET"])
@jwt_required(optional=True)
def get_projects():
    user = current_user()
    # if anonymous, return empty list (frontend will redirect to login for protected pages)
    if not user:
        return jsonify([])
    acc = _accessible_project_ids(user)
    if acc is None:
        projects = Project.query.order_by(Project.id.desc()).all()
    else:
        if not acc:
            projects = []
        else:
            projects = Project.query.filter(Project.id.in_(list(acc))).order_by(Project.id.desc()).all()
    project_list = []
    for p in projects:
        project_list.append({
            "id": p.id,
            "title": getattr(p, 'title', getattr(p, 'name', None)),
            "description": p.description,
            "status": p.status,
            "owner": p.owner.name if p.owner else "Unknown",
            "team_id": getattr(p, 'team_id', None),
        })
    return jsonify(project_list)


# ---------------------------
# ✅ CREATE new project
# ---------------------------
@project_bp.route("/", methods=["POST"])
@jwt_required()
def create_project():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    data = request.json or {}
    title = data.get("title")
    if not title:
        return jsonify({"msg": "title required"}), 400
    p = Project(title=title, description=data.get("description"), owner=user)

    # parse dates
    sd, dl = data.get("start_date"), data.get("deadline")
    try:
        if sd:
            p.start_date = datetime.strptime(sd, "%Y-%m-%d").date()
        if dl:
            p.deadline = datetime.strptime(dl, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"msg": "invalid date format, use YYYY-MM-DD"}), 400

    # optional: associate project with a team if provided and user is a member
    team_id = data.get("team_id")
    if team_id and hasattr(p, "team_id"):
        try:
            tid = int(team_id)
            t = db.session.get(Team, tid)
            # require that only team owners/maintainers or admins can create team-scoped projects
            if not t:
                return jsonify({"msg": "team not found"}), 404
            is_team_manager = False
            try:
                if t.created_by == user.id:
                    is_team_manager = True
                tm = TeamMember.query.filter_by(team_id=t.id, user_id=user.id).first()
                if tm and tm.role in ("owner", "maintainer"):
                    is_team_manager = True
            except Exception:
                is_team_manager = False
            if not (is_team_manager or getattr(user, 'role', None) == RoleEnum.ADMIN):
                return jsonify({"msg": "forbidden: cannot create team project"}), 403
            # attach project to team
            # Attach project to the team (we've already validated permissions). Do not rely solely on the legacy
            # users_teams relationship; set the team_id so TeamMember-based membership will control visibility.
            p.team_id = tid
        except Exception:
            pass

    db.session.add(p)
    db.session.commit()
    # optional: add initial project members if provided
    member_ids = data.get("member_ids") or []
    try:
        if isinstance(member_ids, str):
            # allow CSV string
            member_ids = [int(x.strip()) for x in member_ids.split(",") if x.strip()]
        member_ids = [int(x) for x in (member_ids or [])]
    except Exception:
        member_ids = []

    if member_ids:
        for mid in member_ids:
            u = db.session.get(User, mid)
            if not u:
                continue
            # if project is team-scoped, ensure member belongs to that team
            if getattr(p, 'team_id', None):
                t = db.session.get(Team, p.team_id)
                if not t or u not in (t.members or []):
                    continue
            # attach member
            try:
                pm = ProjectMember(project=p, user=u, role=getattr(u, 'role', None) or 'developer')
                db.session.add(pm)
            except Exception:
                continue

    db.session.add(Activity(actor_id=user.id, verb="created project", target_type="project", target_id=p.id))
    db.session.commit()
    return jsonify({"id": p.id}), 201


# ---------------------------
# ✅ UPDATE / DELETE project
# ---------------------------
@project_bp.route("/<int:project_id>", methods=["PUT", "DELETE"])
@jwt_required()
def modify_project(project_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    p = db.session.get(Project, project_id)
    if not p:
        return jsonify({"msg":"not found"}), 404
    # only allow modification/deletion by project owner or team owner/maintainer
    if p.team_id:
        t = db.session.get(Team, p.team_id)
        is_team_manager = False
        try:
            # team.members is list of users; check if user exists and is owner/maintainer via memberships
            for m in (t.memberships or []):
                if m.user_id == user.id and m.role in ("owner", "maintainer"):
                    is_team_manager = True
                    break
        except Exception:
            is_team_manager = False
        if not (p.owner_id == user.id or is_team_manager or getattr(user, 'role', None) == RoleEnum.ADMIN):
            return jsonify({"msg":"forbidden"}), 403
    else:
        if not (p.owner_id == user.id or getattr(user, 'role', None) == RoleEnum.ADMIN):
            return jsonify({"msg":"forbidden"}), 403

    if request.method == "PUT":
        data = request.json or {}
        p.title = data.get("title", p.title)
        p.description = data.get("description", p.description)
        for key in ("start_date", "deadline"):
            val = data.get(key)
            if val:
                setattr(p, key, datetime.strptime(val, "%Y-%m-%d").date())
        p.status = data.get("status", p.status)
        db.session.commit()
        db.session.add(Activity(actor_id=user.id, verb="updated project", target_type="project", target_id=p.id))
        db.session.commit()
        return jsonify({"msg": "updated"})

    db.session.delete(p)
    db.session.commit()
    db.session.add(Activity(actor_id=user.id, verb="deleted project", target_type="project", target_id=project_id))
    db.session.commit()
    return jsonify({"msg": "deleted"})


# ---------------------------
# ✅ ASSIGN member
# ---------------------------
@project_bp.route("/<int:project_id>/assign", methods=["POST"])
@jwt_required()
def assign_member(project_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    p = Project.query.get_or_404(project_id)
    # Only allow assigning members if project owner or team owner/maintainer
    if p.team_id:
        t = db.session.get(Team, p.team_id)
        can_manage = False
        for m in (t.memberships or []):
            if m.user_id == user.id and m.role in ("owner", "maintainer"):
                can_manage = True
                break
        if not (can_manage or p.owner_id == user.id or getattr(user, 'role', None) == RoleEnum.ADMIN):
            return jsonify({"msg":"forbidden"}), 403
    else:
        if not (p.owner_id == user.id or getattr(user, 'role', None) == RoleEnum.ADMIN):
            return jsonify({"msg":"forbidden"}), 403
    data = request.json or {}
    u = db.session.get(User, data.get("user_id"))
    if not u:
        return jsonify({"msg":"user not found"}), 404
    role = data.get("role", RoleEnum.DEVELOPER)

    existing = ProjectMember.query.filter_by(project_id=p.id, user_id=u.id).first()
    if existing:
        existing.role = role
    else:
        db.session.add(ProjectMember(project=p, user=u, role=role))
    db.session.commit()

    db.session.add(Activity(actor_id=user.id, verb="assigned member", target_type="project", target_id=p.id))
    db.session.commit()

    try:
        socketio.emit("member_assigned", {"project_id": p.id, "user_id": u.id, "user_name": u.name, "role": role}, room=f"project_{p.id}")
    except Exception:
        pass
    return jsonify({"msg": "assigned"}), 201
