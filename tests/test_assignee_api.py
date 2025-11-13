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


def test_profile_and_team_members_endpoints(client, app):
    # register Alice and create a team
    tokA = register_and_login(client, 'alice3@example.com')
    headersA = {'Authorization': f'Bearer {tokA}'}
    r = client.post('/api/teams/', json={'name': 'TeamZ'}, headers=headersA)
    assert r.status_code == 201
    team_id = r.get_json()['id']

    # register Bob
    tokB = register_and_login(client, 'bob3@example.com')
    headersB = {'Authorization': f'Bearer {tokB}'}

    # Bob's profile should return only Bob (used by frontend when no team selected)
    r = client.get('/api/auth/profile', headers=headersB)
    assert r.status_code == 200
    body = r.get_json()
    assert 'user' in body and body['user']['email'] == 'bob3@example.com'

    # team members (before Bob joins) should include only Alice
    r = client.get(f'/api/teams/{team_id}/members', headers=headersA)
    assert r.status_code == 200
    data = r.get_json()
    members = data.get('members') or []
    assert any(m['email'] == 'alice3@example.com' for m in members)
    assert not any(m['email'] == 'bob3@example.com' for m in members)

    # create invite and have Bob join
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'bob3@example.com', 'expires_in_hours': 1}, headers=headersA)
    assert r.status_code == 201
    code = r.get_json()['invite_code']
    r = client.post('/api/teams/join', json={'invite_code': code}, headers=headersB)
    assert r.status_code == 200

    # now team members should include Bob
    r = client.get(f'/api/teams/{team_id}/members', headers=headersA)
    assert r.status_code == 200
    data = r.get_json()
    members = data.get('members') or []
    assert any(m['email'] == 'bob3@example.com' for m in members)
