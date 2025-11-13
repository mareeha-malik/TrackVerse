"""sync users_teams -> team_member

Revision ID: 0003_sync_users_teams_to_teammember
Revises: 0002_add_project_team_id
Create Date: 2025-11-13 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_sync_users_teams_to_teammember'
down_revision = '0002_add_project_team_id'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=conn)
    if 'users_teams' not in meta.tables or 'team_member' not in meta.tables and 'team_member' not in meta.tables:
        # try forgiving table names
        if 'team_member' not in meta.tables and 'team_member' not in meta.tables:
            # nothing to do
            return
    users_teams = meta.tables.get('users_teams')
    # TeamMember table might be named 'team_member' or 'team_member' depending on migrations; try 'team_member' then 'team_member'
    team_member = meta.tables.get('team_member') or meta.tables.get('team_member') or meta.tables.get('teammember')
    if users_teams is None or team_member is None:
        return

    # Insert pairs from users_teams into team_member if not already present
    insert_sql = f"""
    INSERT INTO {team_member.name} (team_id, user_id, role, added_at)
    SELECT ut.team_id, ut.user_id, 'member', CURRENT_TIMESTAMP
    FROM {users_teams.name} ut
    WHERE NOT EXISTS (
      SELECT 1 FROM {team_member.name} tm WHERE tm.team_id = ut.team_id AND tm.user_id = ut.user_id
    )
    """
    try:
        conn.execute(sa.text(insert_sql))
    except Exception:
        # best-effort migration; ignore failures
        pass


def downgrade():
    # no-op: do not remove team_member rows on downgrade
    pass
