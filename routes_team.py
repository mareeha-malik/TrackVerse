from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Team, User, TeamMember, Invite
from utils import send_email
from datetime import datetime, timedelta, timezone
import secrets, string, uuid

team_bp = Blueprint("teams", __name__)

def _can_manage_team(t, user):
    """Return True if user can manage members/invites: owner or maintainer."""
    if not t or not user:
        return False
    if t.created_by == user.id:
        return True
    tm = TeamMember.query.filter_by(team_id=t.id, user_id=user.id).first()
    if tm and tm.role in ("owner", "maintainer"):
        return True
    return False

def current_user():
    ident = get_jwt_identity()
    if ident is None:
        return None
    uid = None
    if isinstance(ident, dict):
        uid = ident.get("id") or ident.get("user_id") or ident.get("uid")
    else:
        uid = ident
    try:
        uid = int(uid)
    except Exception:
        return None
    return db.session.get(User, uid)


@team_bp.route("/", methods=["POST"])
@jwt_required()
def create_team():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"msg":"name required"}), 400
    description = data.get("description")
    invite_code = data.get("invite_code")
    # generate a short unique invite code if not provided
    def gen_invite_code(length=8):
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(10):
            code = ''.join(secrets.choice(alphabet) for _ in range(length))
            if not Team.query.filter_by(invite_code=code).first():
                return code
        # fallback
        return uuid.uuid4().hex[:length].upper()

    if not invite_code:
        invite_code = gen_invite_code()

    t = Team(name=name, description=description, created_by=user.id, invite_code=invite_code)
    db.session.add(t)
    db.session.commit()
    # create TeamMember record for owner
    tm = TeamMember(team_id=t.id, user_id=user.id, role='owner')
    db.session.add(tm)
    # keep backward-compatible users_teams mapping
    try:
        t.members.append(user)
    except Exception:
        pass
    db.session.commit()
    # return invite_code so creator can share it (but don't expose invite codes in list endpoints)
    return jsonify({"id": t.id, "name": t.name, "invite_code": t.invite_code}), 201


@team_bp.route("/", methods=["GET"])
@jwt_required()
def list_teams():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    # return teams with role info when available
    teams = []
    # prefer TeamMember records
    tms = TeamMember.query.filter_by(user_id=user.id).all()
    if tms:
        for tm in tms:
            t = db.session.get(Team, tm.team_id)
            if t:
                d = t.to_dict()
                d['role'] = tm.role
                teams.append(d)
        return jsonify({"teams": teams})
    # fallback to simple relationship
    teams = user.teams or []
    return jsonify({"teams": [t.to_dict() for t in teams]})


@team_bp.route("/join", methods=["POST"])
@jwt_required()
def join_team():
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    data = request.json or {}
    team_id = data.get("team_id")
    invite_code = data.get("invite_code")
    if not team_id and not invite_code:
        return jsonify({"msg":"team_id or invite_code required"}), 400
    team = None
    if team_id:
        try:
            team = db.session.get(Team, int(team_id))
        except Exception:
            team = None
    # prefer invite records
    invite = None
    if invite_code:
        invite = Invite.query.filter_by(invite_code=invite_code, is_active=True).first()
        if invite and invite.expires_at:
            try:
                exp = invite.expires_at
                if exp.tzinfo is None:
                    # treat naive datetimes as UTC
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    invite = None
            except Exception:
                invite = None
        if invite:
            team = db.session.get(Team, invite.team_id)
    if not team and invite_code:
        # fallback to team-level invite_code
        team = Team.query.filter_by(invite_code=invite_code).first()
    if not team:
        return jsonify({"msg":"team not found"}), 404
    # check existing membership
    existing = TeamMember.query.filter_by(team_id=team.id, user_id=user.id).first()
    if existing:
        return jsonify({"msg":"already a member"}), 200
    # create TeamMember record
    tm = TeamMember(team_id=team.id, user_id=user.id, role='member')
    db.session.add(tm)
    try:
        team.members.append(user)
    except Exception:
        pass
    # mark invite used
    if invite:
        invite.used_by = user.id
        invite.used_at = datetime.now(timezone.utc)
        invite.is_active = False
        db.session.add(invite)
    db.session.commit()
    return jsonify({"msg":"joined","team": team.to_dict()})


@team_bp.route("/<int:team_id>/members/<int:user_id>/role", methods=["POST"])
@jwt_required()
def set_member_role(team_id, user_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    # only creator can set roles for now
    # only creator can regenerate
    if not _can_manage_team(t, user):
        return jsonify({"msg":"forbidden"}), 403
    data = request.json or {}
    role = data.get('role')
    if not role:
        return jsonify({"msg":"role required"}), 400
    tm = TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()
    if not tm:
        return jsonify({"msg":"member not found"}), 404
    tm.role = role
    db.session.add(tm)
    db.session.commit()
    return jsonify({"msg":"role updated"})


@team_bp.route("/<int:team_id>/invite", methods=["POST"])
@jwt_required()
def create_invite(team_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    # only creator/owner/maintainer can create invites
    if not _can_manage_team(t, user):
        return jsonify({"msg":"forbidden"}), 403
    data = request.json or {}
    invited_email = data.get('email')
    expires_in = data.get('expires_in_hours')
    # generate invite code
    def gen_code(length=8):
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = ''.join(secrets.choice(alphabet) for _ in range(length))
            if not Invite.query.filter_by(invite_code=code).first():
                return code
        return uuid.uuid4().hex[:length].upper()

    code = gen_code()
    invite = Invite(team_id=team_id, invite_code=code, invited_email=invited_email, created_by=user.id)
    if expires_in:
        try:
            invite.expires_at = datetime.now(timezone.utc) + timedelta(hours=int(expires_in))
        except Exception:
            pass
    db.session.add(invite)
    db.session.commit()
    # optionally send email
    try:
        if invited_email:
            # include a clickable link to open the teams page with the invite code pre-filled
            host = request.host_url.rstrip('/')
            invite_url = f"{host}/teams?invite_code={code}"
            send_email(invited_email, 'You are invited to join a team', f'Invite code: {code}\nJoin here: {invite_url}')
    except Exception:
        pass
    return jsonify({"id": invite.id, "invite_code": invite.invite_code, "expires_at": invite.expires_at.isoformat() if invite.expires_at else None}), 201


@team_bp.route("/<int:team_id>/invites", methods=["GET"])
@jwt_required()
def list_invites(team_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    # only creator/maintainer can set roles
    if not _can_manage_team(t, user):
        return jsonify({"msg":"forbidden"}), 403
    invites = Invite.query.filter_by(team_id=team_id).order_by(Invite.created_at.desc()).all()
    out = []
    for inv in invites:
        out.append({"id": inv.id, "invite_code": inv.invite_code, "invited_email": inv.invited_email, "expires_at": inv.expires_at.isoformat() if inv.expires_at else None, "is_active": inv.is_active})
    return jsonify({"invites": out})


@team_bp.route("/<int:team_id>/invites/<int:invite_id>", methods=["DELETE"])
@jwt_required()
def revoke_invite(team_id, invite_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    if t.created_by != user.id:
        return jsonify({"msg":"forbidden"}), 403
    inv = db.session.get(Invite, invite_id)
    if not inv:
        return jsonify({"msg":"not found"}), 404
    inv.is_active = False
    db.session.add(inv)
    db.session.commit()
    return jsonify({"msg":"revoked"})


@team_bp.route("/<int:team_id>/members", methods=["GET"])
@jwt_required()
def team_members(team_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    # pagination
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except Exception:
        page = 1; per_page = 20
    q = TeamMember.query.filter_by(team_id=team_id)
    total = q.count()
    items = q.order_by(TeamMember.added_at.desc()).offset((page-1)*per_page).limit(per_page).all()
    out = []
    for im in items:
        u = db.session.get(User, im.user_id)
        out.append({"id": u.id, "name": u.name or u.email, "email": u.email, "role": im.role, "added_at": im.added_at.isoformat()})
    return jsonify({"total": total, "page": page, "per_page": per_page, "members": out})


@team_bp.route("/<int:team_id>", methods=["GET"])
@jwt_required()
def team_detail(team_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    out = t.to_dict()
    # only include invite_code for creator
    if t.created_by == (user.id if user else None):
        out["invite_code"] = t.invite_code
    return jsonify(out)


@team_bp.route("/<int:team_id>/members/<int:user_id>", methods=["DELETE"])
@jwt_required()
def remove_member(team_id, user_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"msg":"user not found"}), 404
    # only creator/maintainer can remove others; users may remove themselves
    if user.id != user_id and not _can_manage_team(t, user):
        return jsonify({"msg":"forbidden"}), 403
    # prevent removing the creator
    if target.id == t.created_by:
        return jsonify({"msg":"cannot remove team creator"}), 400
    if target in t.members:
        t.members.remove(target)
        db.session.add(t)
        db.session.commit()
        return jsonify({"msg":"removed"})
    return jsonify({"msg":"not a member"}), 400


@team_bp.route("/<int:team_id>/invite/regenerate", methods=["POST"])
@jwt_required()
def regenerate_invite(team_id):
    user = current_user()
    if not user:
        return jsonify({"msg":"unauthorized"}), 401
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({"msg":"not found"}), 404
    # only creator can regenerate
    if t.created_by != user.id:
        return jsonify({"msg":"forbidden"}), 403
    # regenerate unique code
    def gen_invite_code(length=8):
        import secrets, string, uuid
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = ''.join(secrets.choice(alphabet) for _ in range(length))
            if not Team.query.filter_by(invite_code=code).first():
                return code
        return uuid.uuid4().hex[:length].upper()

    t.invite_code = gen_invite_code()
    db.session.add(t)
    db.session.commit()
    return jsonify({"invite_code": t.invite_code})
