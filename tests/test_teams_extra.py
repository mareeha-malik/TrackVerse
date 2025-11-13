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


def test_expired_invite_cannot_be_used(client):
    tok1 = register_and_login(client, 'owner2@example.com')
    headers1 = {'Authorization': f'Bearer {tok1}'}
    # create team
    r = client.post('/api/teams/', json={'name': 'Expire Team'}, headers=headers1)
    assert r.status_code == 201
    team = r.get_json()
    team_id = team['id']

    # create invite with negative expiry -> already expired
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'soon@example.com', 'expires_in_hours': -1}, headers=headers1)
    assert r.status_code == 201
    inv = r.get_json()
    code = inv['invite_code']

    # user tries to join with expired invite
    tok2 = register_and_login(client, 'soon@example.com')
    headers2 = {'Authorization': f'Bearer {tok2}'}
    r = client.post('/api/teams/join', json={'invite_code': code}, headers=headers2)
    # expired invite should fail (team not found for invite)
    assert r.status_code == 404


def test_permission_denied_revoking_and_role_changes(client):
    # owner creates team and invite
    tok1 = register_and_login(client, 'owner3@example.com')
    headers1 = {'Authorization': f'Bearer {tok1}'}
    r = client.post('/api/teams/', json={'name': 'Perm Team'}, headers=headers1)
    assert r.status_code == 201
    team = r.get_json(); team_id = team['id']

    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'member@example.com', 'expires_in_hours': 1}, headers=headers1)
    assert r.status_code == 201
    inv = r.get_json(); inv_code = inv['invite_code']

    # member joins
    tok2 = register_and_login(client, 'member@example.com')
    headers2 = {'Authorization': f'Bearer {tok2}'}
    r = client.post('/api/teams/join', json={'invite_code': inv_code}, headers=headers2)
    assert r.status_code == 200

    # member attempts to revoke invite (should be forbidden)
    # find invite id
    r = client.get(f'/api/teams/{team_id}/invites', headers=headers1)
    invites = r.get_json()['invites']
    assert len(invites) >= 1
    inv_id = invites[0]['id']

    r = client.delete(f'/api/teams/{team_id}/invites/{inv_id}', headers=headers2)
    assert r.status_code == 403

    # member cannot create invites until promoted
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'x@example.com'}, headers=headers2)
    assert r.status_code == 403

    # owner promotes member to maintainer
    # find member id
    r = client.get(f'/api/teams/{team_id}/members', headers=headers1)
    members = r.get_json()['members']
    m = next((m for m in members if m['email']=='member@example.com'), None)
    assert m
    uid = m['id']

    r = client.post(f'/api/teams/{team_id}/members/{uid}/role', json={'role': 'maintainer'}, headers=headers1)
    assert r.status_code == 200

    # now member can create invites
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'new@example.com'}, headers=headers2)
    assert r.status_code == 201
