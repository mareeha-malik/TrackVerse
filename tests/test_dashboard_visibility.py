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


def test_new_user_sees_zero_projects_and_bugs(client):
    tok = register_and_login(client, 'newuser@example.com')
    headers = {'Authorization': f'Bearer {tok}'}

    r = client.get('/api/projects/', headers=headers)
    assert r.status_code == 200
    assert r.get_json() == []

    r = client.get('/api/bugs/', headers=headers)
    assert r.status_code == 200
    assert r.get_json() == []

    r = client.get('/api/bugs/analytics/summary', headers=headers)
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('demo') is False
    assert data.get('total_projects') == 0
    assert data.get('total_bugs') == 0


def test_personal_and_team_project_visibility(client):
    # user A creates a personal project
    tokA = register_and_login(client, 'alice@example.com')
    hA = {'Authorization': f'Bearer {tokA}'}
    r = client.post('/api/projects/', json={'title': 'Alice Project'}, headers=hA)
    assert r.status_code == 201
    pid = r.get_json()['id']

    # Alice sees her project
    r = client.get('/api/projects/', headers=hA)
    assert any(p['id'] == pid for p in r.get_json())

    # Create team and team project
    r = client.post('/api/teams/', json={'name': 'TeamX'}, headers=hA)
    assert r.status_code == 201
    team_id = r.get_json()['id']

    # create a team-scoped project as Alice (owner/member)
    r = client.post('/api/projects/', json={'title': 'Team Project', 'team_id': team_id}, headers=hA)
    assert r.status_code == 201
    team_pid = r.get_json()['id']

    # Bob registers and joins the team
    tokB = register_and_login(client, 'bob@example.com')
    hB = {'Authorization': f'Bearer {tokB}'}
    # create invite
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'bob@example.com', 'expires_in_hours': 1}, headers=hA)
    assert r.status_code == 201
    code = r.get_json()['invite_code']
    r = client.post('/api/teams/join', json={'invite_code': code}, headers=hB)
    assert r.status_code == 200

    # Bob should now see the team project
    r = client.get('/api/projects/', headers=hB)
    projects = r.get_json()
    assert any(p['id'] == team_pid for p in projects)
