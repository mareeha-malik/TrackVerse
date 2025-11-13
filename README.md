TrackVerse - minimal Flask starter
1. Create a virtualenv and install requirements:
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt

2. Edit config in .env or config.py (MAIL settings).

3. Run:
   python app.py

This will create an SQLite database 'trackverse.db'. Use the API endpoints under /api/.

Teams (new)
----------------
This project now includes a basic Team/Room system.

- Models: `Team` model and `users_teams` association table were added. `Team` fields: id, name, description, created_by, created_at, optional invite_code. `User.teams` and `Team.members` relationships are available via SQLAlchemy.
- Endpoints (new):
   - POST /api/teams/        -> create a new team (JSON: name, description, invite_code)
   - GET  /api/teams/        -> list teams the current user belongs to
   - POST /api/teams/join    -> join a team by team_id or invite_code
   - GET  /api/teams/<id>/members -> list members of a team

Frontend: the bug creation modal now contains a "Team" dropdown showing teams the creator belongs to; choosing a team will populate the "Assignee" dropdown with only that team's members. The backend validates assignee/team membership while preserving backward compatibility for users/projects without teams.

Database/migrations:
If you use Flask-Migrate / Alembic, run your normal migration commands (e.g. `flask db migrate` / `flask db upgrade`) after pulling these changes, or drop and recreate the DB for testing. The app will also call `db.create_all()` on startup for quick local testing.

Windows helper (PowerShell)
---------------------------
If you're on Windows (PowerShell) you can use the included helper script to run migrations. It will set the `FLASK_APP` environment variable and run `flask db` commands. Review the generated migration before applying to production.

Run this from the repository root (PowerShell):

```powershell
# activate your virtualenv
venv\Scripts\Activate

# (only once) initialize the migrations folder
$env:FLASK_APP = 'app.py'
flask db init

# autogenerate a migration (review the generated file under migrations/versions)
flask db migrate -m "add teams and invites"

# apply it to the DB
flask db upgrade
```

Or use the helper script (wrapper around the commands above):

```powershell
.\scripts\run_migrations.ps1 -Message "add teams and invites"
```

Important: always inspect the migration file generated under `migrations/versions` before running `flask db upgrade` in production. Alembic's autogeneration may not detect every change (indexes, constraints) and the migration may need manual edits.

Running tests
--------------
We added pytest-based unit tests for Teams flows. Install pytest into your virtualenv and run tests:

```powershell
venv\Scripts\Activate
pip install pytest
python -m pytest -q
```

This runs the in-repo tests under `tests/` which use an in-memory SQLite instance.

Teams management UI
-------------------
There are two team-facing pages:
- `/teams` — simple create/join/list UI.
- `/teams/manage?team_id=<id>` — dedicated management UI (requires you be the team owner to create invites and manage members).

Make sure you're logged in (the UI stores the JWT in `localStorage.tv_token`).
