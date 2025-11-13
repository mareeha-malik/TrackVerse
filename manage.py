import os
import click
from app import create_app
from extensions import db, socketio
from flask_migrate import migrate as _migrate, upgrade as _upgrade, init as _init, revision as _revision

app = create_app()

@click.group()
def cli():
    """Management script for TrackVerse"""
    pass

@cli.command("run")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=5000, type=int)
@click.option("--debug/--no-debug", default=True)
def run(host, port, debug):
    """Run the app with SocketIO"""
    socketio.run(app, host=host, port=port, debug=debug)

@cli.command("create-admin")
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--name", default="Administrator")
def create_admin(email, password, name):
    """Create an admin user (if not exists)"""
    from models import User, RoleEnum
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        if u:
            click.echo(f"User {email} already exists (id={u.id})")
            return
        u = User(email=email, name=name, role=RoleEnum.ADMIN)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Created admin user {email} (id={u.id})")

@cli.command("db-migrate")
@click.option("--message", "-m", default="auto migration")
def db_migrate(message):
    """Autogenerate a migration (uses Flask-Migrate internals)"""
    with app.app_context():
        try:
            _migrate(message=message)
            click.echo("Migration script generated.")
        except Exception as e:
            click.echo(f"Migration failed: {e}")

@cli.command("db-upgrade")
def db_upgrade():
    """Apply DB migrations (upgrade)"""
    with app.app_context():
        try:
            _upgrade()
            click.echo("Database upgraded.")
        except Exception as e:
            click.echo(f"Upgrade failed: {e}")

if __name__ == "__main__":
    cli()