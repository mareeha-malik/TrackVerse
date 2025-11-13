import os
import time
import json
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
from werkzeug.utils import secure_filename
from flask_mail import Message
from app import mail

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

def generate_token(email, purpose="confirm"):
    s = get_serializer()
    return s.dumps({"email": email, "purpose": purpose})

def confirm_token(token, max_age=3600):
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        return data
    except Exception:
        return None

def send_email(to, subject, body):
    """
    Send an email if SMTP is configured. On missing/unreachable SMTP server,
    log a warning and return False (do not raise).
    """
    try:
        mail_server = current_app.config.get("MAIL_SERVER")
        mail_user = current_app.config.get("MAIL_USERNAME")
        # If no explicit SMTP configured (default localhost) and no credentials, skip sending in dev
        if not mail_server or (mail_server in ("localhost", "127.0.0.1") and not mail_user):
            current_app.logger.info("send_email skipped: MAIL_SERVER not configured for outbound mail.")
            return False

        msg = Message(subject=subject, recipients=[to], body=body, sender=current_app.config.get("MAIL_USERNAME"))
        mail.send(msg)
        return True
    except Exception as ex:
        # avoid noisy stack trace for transient SMTP failures during dev
        current_app.logger.warning("send_email failed: %s", str(ex))
        return False

ALLOWED_EXT = {"png","jpg","jpeg","gif","txt","log","pdf","py"}
def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT

def save_upload(file_storage):
    filename = secure_filename(file_storage.filename)
    folder = current_app.config['UPLOAD_FOLDER']
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{int(time.time())}{ext}"
        path = os.path.join(folder, filename)
    file_storage.save(path)
    return filename, path

def scan_python_syntax(file_path):
    """
    Returns list of dicts for syntax errors found, empty list if none.
    """
    errors = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            src = f.read()
        # attempt compile to capture SyntaxError
        compile(src, file_path, "exec")
    except SyntaxError as e:
        errors.append({"lineno": getattr(e, "lineno", None), "msg": str(e)})
    except Exception as e:
        # other IO/encoding issues
        errors.append({"lineno": None, "msg": str(e)})
    return errors

def auto_create_syntax_bugs(project_id, reporter, filename, filepath):
    """
    If the file is a .py file and contains syntax errors, auto-create Bug entries.
    Import models/db lazily to avoid circular imports.
    """
    from app import db
    from models import Bug, Attachment, SeverityEnum
    errors = scan_python_syntax(filepath)
    created = []
    for err in errors:
        title = f"Syntax error in {filename} (line {err.get('lineno')}"
        b = Bug(title=title,
                description=f"Detected by automated scanner: {err.get('msg')}",
                project_id=project_id,
                severity=SeverityEnum.MAJOR,
                reporter=reporter)
        db.session.add(b)
        db.session.commit()
        # attach original file as attachment record
        att = Attachment(bug_id=b.id, filename=filename, filepath=filepath)
        db.session.add(att)
        db.session.commit()
        created.append({"bug_id": b.id, "title": b.title})
    return created


def get_visible_users(caller=None, team_id=None):
    """Return a list of user dicts visible to `caller`.

    Rules:
    - If team_id provided, return members of that team.
    - If caller is admin, return all users.
    - If caller belongs to teams, return users who share those teams.
    - Otherwise return only the caller (or empty list if anonymous).
    """
    try:
        from extensions import db
        from models import User, Team, TeamMember, RoleEnum
    except Exception:
        return []

    # team-specific fast path
    if team_id is not None:
        try:
            tid = int(team_id)
            t = db.session.get(Team, tid)
            if not t:
                return []
            members = t.members or []
            return [{"id": u.id, "name": u.name or u.email, "email": u.email, "role": getattr(u, 'role', None)} for u in members]
        except Exception:
            return []

    # admin sees everyone
    if caller and getattr(caller, 'role', None) == RoleEnum.ADMIN:
        users = User.query.all()
        return [{"id": u.id, "name": u.name or u.email, "email": u.email, "role": getattr(u, 'role', None)} for u in users]

    # caller's teammates
    if caller and (caller.teams or []):
        team_member_ids = set()
        for t in caller.teams:
            for m in (t.members or []):
                if getattr(m, 'id', None):
                    team_member_ids.add(m.id)
        if team_member_ids:
            users = User.query.filter(User.id.in_(list(team_member_ids))).all()
            return [{"id": u.id, "name": u.name or u.email, "email": u.email, "role": getattr(u, 'role', None)} for u in users]

    # fallback: only the caller
    if caller:
        return [{"id": caller.id, "name": caller.name or caller.email, "email": caller.email, "role": getattr(caller, 'role', None)}]
    return []
