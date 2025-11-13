"""add project.team_id

Revision ID: 0002_add_project_team_id
Revises: 0001_add_teams_invites
Create Date: 2025-11-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_project_team_id'
down_revision = '0001_add_teams_invites'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('project', sa.Column('team_id', sa.Integer(), nullable=True))
        # try adding FK if supported
        try:
            op.create_foreign_key('fk_project_team', 'project', 'team', ['team_id'], ['id'])
        except Exception:
            pass
    except Exception:
        # ignore if column exists
        pass


def downgrade():
    try:
        op.drop_constraint('fk_project_team', 'project', type_='foreignkey')
    except Exception:
        pass
    try:
        op.drop_column('project', 'team_id')
    except Exception:
        pass
