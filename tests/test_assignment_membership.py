import pytest
from app import create_app
from extensions import db


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def register_and_login(client, email, password='pass'):
    r = client.post('/api/auth/register', json={'email': email, 'password': password, 'name': email.split('@')[0]})
    assert r.status_code == 201
    r = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert r.status_code == 200
    data = r.get_json()
    token = data.get('access_token')
    return token


def test_project_creation_respects_team_membership(client, app):
    # Alice creates team
    tokA = register_and_login(client, 'alice2@example.com')
    hA = {'Authorization': f'Bearer {tokA}'}
    r = client.post('/api/teams/', json={'name': 'TeamY'}, headers=hA)
    assert r.status_code == 201
    team_id = r.get_json()['id']

    # register Bob (not yet a member)
    tokB = register_and_login(client, 'bob2@example.com')

    # get bob id from DB
    with app.app_context():
        from models import User, ProjectMember
        bob = User.query.filter_by(email='bob2@example.com').first()
        assert bob is not None
        bob_id = bob.id

    # Alice creates a team-scoped project but includes Bob in member_ids (Bob is not a member yet)
    r = client.post('/api/projects/', json={'title': 'Team Project 2', 'team_id': team_id, 'member_ids': [bob_id]}, headers=hA)
    assert r.status_code == 201
    pid = r.get_json()['id']

    # ensure ProjectMember table has no entry for Bob (since he's not a team member)
    with app.app_context():
        from models import ProjectMember
        pm = ProjectMember.query.filter_by(project_id=pid, user_id=bob_id).first()
        assert pm is None

    # Create an invite and have Bob join
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'bob2@example.com', 'expires_in_hours': 1}, headers=hA)
    assert r.status_code == 201
    code = r.get_json()['invite_code']
    # Bob joins using invite
    r = client.post('/api/teams/join', json={'invite_code': code}, headers={'Authorization': f'Bearer {tokB}'})
    assert r.status_code == 200

    # Alice creates another project and includes Bob
    r = client.post('/api/projects/', json={'title': 'Team Project 3', 'team_id': team_id, 'member_ids': [bob_id]}, headers=hA)
    assert r.status_code == 201
    pid2 = r.get_json()['id']

    # Now Bob should be a project member
    with app.app_context():
        from models import ProjectMember
        pm2 = ProjectMember.query.filter_by(project_id=pid2, user_id=bob_id).first()
        assert pm2 is not None
        assert pm2.user_id == bob_id
