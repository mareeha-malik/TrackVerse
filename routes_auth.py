from flask import Blueprint, request, jsonify
from extensions import db
from models import User, Activity, RoleEnum, Team
from utils import generate_token, confirm_token, send_email
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt

auth_bp = Blueprint("auth", __name__)

# Helper to get current user
def current_user():
    """Return User or None. Accepts either an int identity or a dict containing 'id'."""
    try:
        ident = get_jwt_identity()
        if ident is None:
            return None
        uid = None
        if isinstance(ident, dict):
            uid = ident.get("id") or ident.get("user_id") or ident.get("uid")
        else:
            uid = ident
        uid = int(uid)
        return db.session.get(User, uid)
    except Exception:
        return None

# REGISTER
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    email = data.get("email")
    pw = data.get("password")
    name = data.get("name")
    role = data.get("role", RoleEnum.DEVELOPER)
    if not email or not pw:
        return jsonify({"msg": "email and password required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "email exists"}), 400

    u = User(email=email, name=name, role=role)
    u.set_password(pw)
    db.session.add(u)
    db.session.commit()

    token = generate_token(email, purpose="confirm")
    try:
        send_email(email, "Confirm your TrackVerse account", f"Confirm token: {token}")
    except Exception:
        pass

    act = Activity(actor_id=u.id, verb="registered", target_type="user", target_id=u.id)
    db.session.add(act)
    db.session.commit()
    return jsonify({"msg": "registered", "user_id": u.id}), 201


# CONFIRM
@auth_bp.route("/confirm/<token>")
def confirm_email(token):
    data = confirm_token(token)
    if not data or data.get("purpose") != "confirm":
        return jsonify({"msg": "invalid or expired token"}), 400
    email = data.get("email")
    u = User.query.filter_by(email=email).first()
    if not u:
        return jsonify({"msg": "user not found"}), 404
    u.email_confirmed = True
    db.session.commit()
    return jsonify({"msg": "email confirmed"})


# LOGIN
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    pw = data.get("password")
    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(pw):
        return jsonify({"msg": "bad credentials"}), 401

    token = create_access_token(identity=str(u.id), additional_claims={"role": u.role})

    act = Activity(actor_id=u.id, verb="logged in", target_type="user", target_id=u.id)
    db.session.add(act)
    db.session.commit()

    return jsonify({
        "access_token": token,
        "user": {"id": u.id, "email": u.email, "name": u.name, "role": u.role}
    })


# LOGOUT
@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    user = current_user()
    if user:
        act = Activity(actor_id=user.id, verb="logged out", target_type="user", target_id=user.id)
        db.session.add(act)
        db.session.commit()
    return jsonify({"msg": "logged out"})


# DASHBOARD REDIRECT
@auth_bp.route("/dashboard_redirect", methods=["GET"])
@jwt_required()
def dashboard_redirect():
    claims = get_jwt()
    role = claims.get("role")

    if role == RoleEnum.ADMIN:
        target = "/admin/overview"
    elif role == RoleEnum.PM:
        target = "/projects/overview"
    elif role == RoleEnum.DEVELOPER:
        target = "/bugs/assigned"
    elif role == RoleEnum.TESTER:
        target = "/bugs/reported"
    else:
        target = "/"

    return jsonify({"redirect": target})


# PROFILE / ME endpoint
@auth_bp.route("/profile", methods=["GET", "PUT"])
@auth_bp.route("/me", methods=["GET", "PUT"])
@jwt_required()
def profile():
    user = current_user()
    if not user:
        return jsonify({"msg": "user not found"}), 404

    if request.method == "GET":
        return jsonify({
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "avatar": user.avatar if hasattr(user, 'avatar') else None
            }
        })
    
    data = request.json or {}
    user.name = data.get("name", user.name)
    if hasattr(user, 'avatar'):
        user.avatar = data.get("avatar", user.avatar)
    if data.get("password"):
        user.set_password(data.get("password"))
    db.session.commit()

    act = Activity(actor_id=user.id, verb="updated profile", target_type="user", target_id=user.id)
    db.session.add(act)
    db.session.commit()
    return jsonify({"msg": "updated"})


# LIST USERS endpoint (for dropdowns)
@auth_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    """Return list of users for assignment dropdowns.

    Behavior:
    - If `team_id` query param provided, return that team's members (paginated).
    - If caller is admin, return all users.
    - If caller belongs to at least one team, return users who share any team with caller.
    - Otherwise return only the caller (so new users don't see everyone).
    """
    caller = current_user()
    team_id = request.args.get("team_id")
    from utils import get_visible_users
    users = get_visible_users(caller=caller, team_id=team_id)
    return jsonify({"users": users})