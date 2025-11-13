import os
from flask import Flask, jsonify, render_template, request, redirect, url_for
try:
    from flask_cors import CORS
except Exception:
    def CORS(app, **kwargs):
        try:
            app.logger.warning("flask_cors not installed; CORS not enabled")
        except Exception:
            pass
        return None
from config import Config

from extensions import db, jwt, mail, socketio, migrate
from flask_jwt_extended import decode_token, jwt_required, get_jwt_identity
import jwt as pyjwt
from jwt.exceptions import InvalidSubjectError

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    os.makedirs(app.config.get("UPLOAD_FOLDER", os.path.join(os.path.abspath(os.path.dirname(__file__)), "uploads")), exist_ok=True)

    CORS(app)
    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)

    from routes_auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    try:
        from routes_project import project_bp
        app.register_blueprint(project_bp, url_prefix="/api/projects")
    except Exception:
        pass

    try:
        from routes_team import team_bp
        app.register_blueprint(team_bp, url_prefix="/api/teams")
    except Exception:
        pass

    try:
        from routes_bug import bug_bp
        app.register_blueprint(bug_bp, url_prefix="/api/bugs")
    except Exception:
        pass

    @app.route("/")
    def home_page():
        return render_template("index.html")

    @app.route("/login")
    def login_page():
        return render_template("login.html")

    @app.route("/register")
    def register_page():
        return render_template("register.html")

    @app.route("/dashboard")
    def dashboard_page():
        return render_template("dashboard.html")

    @app.route("/projects")
    def projects_page():
        return render_template("projects.html")

    @app.route("/teams")
    def teams_page():
        return render_template("teams.html")
    @app.route("/teams/<int:team_id>")
    def teams_detail_redirect(team_id):
        # Redirect legacy /teams/<id> links to the management UI which accepts a team_id query param
        return redirect(url_for('teams_manage_page') + f"?team_id={team_id}")
    @app.route("/teams/manage")
    def teams_manage_page():
        return render_template("teams_manage.html")

    @app.route("/projects/<int:project_id>")
    def project_detail_page(project_id):
        return render_template("project_detail.html", project_id=project_id)

    @app.route("/bugs")
    def bugs_page():
        return render_template("bugs.html")

    @app.route("/bugs/<int:bug_id>")
    def bug_detail_page(bug_id):
        return render_template("bug_detail.html", bug_id=bug_id)

    # Legacy-friendly route: accept /bugs/<id>/edit and serve the same detail page.
    # The client-side JS in `bug_detail.html` will detect the `/edit` path and
    # redirect to `/bugs/<id>?edit=1` or open the edit UI. This prevents 404s
    # when users or old links navigate to /bugs/123/edit.
    @app.route("/bugs/<int:bug_id>/edit")
    def bug_detail_edit_page(bug_id):
        return render_template("bug_detail.html", bug_id=bug_id)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # Add /api/users endpoint for user list (used by frontend dropdowns)
    @app.route("/api/users", methods=["GET"])
    @jwt_required()
    def list_users():
        """Return list of all users for assignment dropdowns"""
        try:
            from models import User, Team
            # determine caller
            # determine caller
            try:
                ident = get_jwt_identity()
                uid = None
                if isinstance(ident, dict):
                    uid = ident.get("id") or ident.get("user_id") or ident.get("uid")
                else:
                    uid = ident
                caller = db.session.get(User, int(uid)) if uid is not None else None
            except Exception:
                caller = None

            # Delegate visibility logic to helper
            from utils import get_visible_users
            team_id = request.args.get('team_id')
            users = get_visible_users(caller=caller, team_id=team_id)
            return jsonify({"users": users})
        except Exception as e:
            app.logger.error(f"Error fetching users: {e}")
            return jsonify({"msg": "Error fetching users", "users": []}), 500

    with app.app_context():
        try:
            from models import User, Project, Bug, Comment, Attachment, Activity, ProjectMember
            db.create_all()
        except Exception:
            pass

    from flask_socketio import join_room, leave_room

    @socketio.on("connect")
    def _socket_connect(auth):
        token = None
        if isinstance(auth, dict):
            token = auth.get("token") or auth.get("access_token") or auth.get("jwt")
        if not token:
            token = request.args.get("token", None)

        if not token:
            app.logger.debug("Socket connect: no token provided; allowing anonymous connection")
            decoded = None
        else:
            try:
                decoded = decode_token(token)
            except InvalidSubjectError:
                try:
                    payload = pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})
                    sub = payload.get("sub")
                    if isinstance(sub, dict):
                        identity = str(sub.get("id") if sub.get("id") is not None else sub)
                    else:
                        identity = str(sub)
                    decoded = {"sub": identity, **{k: v for k, v in payload.items() if k != "sub"}}
                except Exception:
                    app.logger.debug("Socket connect: token payload could not be decoded, continuing as anonymous")
                    decoded = None
            except Exception as e:
                app.logger.debug("Socket connect: token decode failed (%s), continuing as anonymous", e)
                decoded = None

        try:
            user_identity = decoded.get("sub") if decoded else None
            if user_identity:
                try:
                    join_room(f"user_{user_identity}")
                except Exception:
                    app.logger.debug("Failed to join user room for %s", user_identity)
                app.logger.info("Socket connect accepted: user=%s", user_identity)
            else:
                app.logger.info("Socket connect accepted: anonymous")
        except Exception:
            app.logger.exception("Socket connect processing failed")
            return False

        return True

    @socketio.on("join_project")
    def _socket_join_project(data):
        try:
            project_id = int(data.get("project_id"))
            join_room(f"project_{project_id}")
        except Exception:
            app.logger.exception("join_project failed")

    @socketio.on("leave_project")
    def _socket_leave_project(data):
        try:
            project_id = int(data.get("project_id"))
            leave_room(f"project_{project_id}")
        except Exception:
            app.logger.exception("leave_project failed")

    return app

if __name__ == "__main__":
    app = create_app()
    try:
        socketio.run(app, host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    except OSError as e:
        msg = str(e)
        if getattr(e, "winerror", None) == 10048 or "Address already in use" in msg or "EADDRINUSE" in msg:
            app.logger.error("Port 5000 already in use. Attempting fallback port 5001.")
            try:
                socketio.run(app, host="127.0.0.1", port=5001, debug=False, use_reloader=False)
            except Exception:
                app.logger.exception("Failed to start server on fallback port 5001.")
        else:
            app.logger.exception("Server failed to start")
            raise