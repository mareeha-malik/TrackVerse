"""add teams, memberships, invites and bug.team_id

Revision ID: 0001_add_teams_invites
Revises: 
Create Date: 2025-11-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_add_teams_invites'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # teams table
    op.create_table(
        'team',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('invite_code', sa.String(64), nullable=True),
    )

    # users_teams association table (legacy)
    op.create_table(
        'users_teams',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('team.id'), primary_key=True),
    )

    # team_member association object
    op.create_table(
        'team_member',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('team.id')),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id')),
        sa.Column('role', sa.String(50), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=True),
    )

    # invite table
    op.create_table(
        'invite',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('team.id'), nullable=False),
        sa.Column('invite_code', sa.String(64), nullable=False),
        sa.Column('invited_email', sa.String(120), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('used_by', sa.Integer(), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.sql.expression.true()),
    )

    # add team_id to bug table
    try:
        op.add_column('bug', sa.Column('team_id', sa.Integer(), sa.ForeignKey('team.id'), nullable=True))
    except Exception:
        # in case table/column exists or DB doesn't support FK add, ignore
        pass


def downgrade():
    try:
        op.drop_column('bug', 'team_id')
    except Exception:
        pass
    op.drop_table('invite')
    op.drop_table('team_member')
    op.drop_table('users_teams')
    op.drop_table('team')
