from datetime import datetime, date, timezone
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
import json

class RoleEnum:
    ADMIN = "admin"
    PM = "project_manager"
    DEVELOPER = "developer"
    TESTER = "tester"

class ProjectStatus:
    ACTIVE = "Active"
    COMPLETED = "Completed"
    ARCHIVED = "Archived"

class BugPriority:
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

class SeverityEnum:
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"

class BugStatus:
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(50), default=RoleEnum.DEVELOPER)
    is_active = db.Column(db.Boolean, default=True)
    email_confirmed = db.Column(db.Boolean, default=False)
    avatar = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

# association table for users <> teams
users_teams = db.Table(
    'users_teams',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('team_id', db.Integer, db.ForeignKey('team.id'), primary_key=True)
)

# add relationship on the User model for convenience
if not hasattr(User, 'teams'):
    User.teams = db.relationship('Team', secondary=users_teams, back_populates='members')

# New association object for richer membership data (role, timestamps)
class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    role = db.Column(db.String(50), default='member')  # owner/member/maintainer
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    team = db.relationship('Team', back_populates='memberships')
    user = db.relationship('User')


class Invite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    invite_code = db.Column(db.String(64), nullable=False, index=True)
    invited_email = db.Column(db.String(120), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    used_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    team = db.relationship('Team')

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=True)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default=ProjectStatus.ACTIVE)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    owner = db.relationship("User", foreign_keys=[owner_id])
    # optional: associate a project with a team (nullable for personal projects)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)
    team = db.relationship("Team")
    members = db.relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    role = db.Column(db.String(50), default=RoleEnum.DEVELOPER)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    project = db.relationship("Project", back_populates="members")
    user = db.relationship("User")

class Bug(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    severity = db.Column(db.String(50), default=SeverityEnum.MAJOR)
    priority = db.Column(db.String(50), default=BugPriority.MEDIUM)
    status = db.Column(db.String(50), default=BugStatus.OPEN)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"))
    project = db.relationship("Project")
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    reporter = db.relationship("User", foreign_keys=[reporter_id])
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assignee = db.relationship("User", foreign_keys=[assignee_id])
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    comments = db.relationship("Comment", back_populates="bug", cascade="all, delete-orphan")
    attachments = db.relationship("Attachment", back_populates="bug", cascade="all, delete-orphan")

    # optional: team assignment (for future filtering/permissions)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)
    team = db.relationship("Team")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey("bug.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    body = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    bug = db.relationship("Bug", back_populates="comments")
    user = db.relationship("User")

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.Integer, db.ForeignKey("bug.id"))
    filename = db.Column(db.String(256))
    filepath = db.Column(db.String(512))
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    bug = db.relationship("Bug", back_populates="attachments")

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    verb = db.Column(db.String(200))
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    meta = db.Column(db.Text)  # JSON string for extra info

    actor = db.relationship("User", foreign_keys=[actor_id])

    def set_meta(self, d):
        self.meta = json.dumps(d)

    def get_meta(self):
        try:
            return json.loads(self.meta or "{}")
        except Exception:
            return {}


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # optional invite code (simple string); can be null
    invite_code = db.Column(db.String(64), nullable=True, unique=False)

    # backrefs
    members = db.relationship('User', secondary=users_teams, back_populates='teams')
    # richer membership records
    memberships = db.relationship('TeamMember', back_populates='team', cascade='all, delete-orphan')

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description, "created_by": self.created_by}
