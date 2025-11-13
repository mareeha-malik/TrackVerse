import pytest
from app import create_app
from extensions import db
import json


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


def test_create_join_regen_remove_flow(client):
    # creator
    tok1 = register_and_login(client, 'owner@example.com')
    headers1 = {'Authorization': f'Bearer {tok1}'}

    # create team
    r = client.post('/api/teams/', json={'name': 'Test Team'}, headers=headers1)
    assert r.status_code == 201
    team = r.get_json()
    team_id = team['id']

    # create invite
    r = client.post(f'/api/teams/{team_id}/invite', json={'email': 'invitee@example.com', 'expires_in_hours': 1}, headers=headers1)
    assert r.status_code == 201
    inv = r.get_json()
    code = inv['invite_code']

    # second user registers and joins using invite
    tok2 = register_and_login(client, 'invitee@example.com')
    headers2 = {'Authorization': f'Bearer {tok2}'}
    r = client.post('/api/teams/join', json={'invite_code': code}, headers=headers2)
    assert r.status_code == 200

    # list members page
    r = client.get(f'/api/teams/{team_id}/members', headers=headers1)
    data = r.get_json()
    assert data['total'] >= 2

    # regenerate invite
    r = client.post(f'/api/teams/{team_id}/invite/regenerate', headers=headers1)
    assert r.status_code == 200
    newcode = r.get_json().get('invite_code')
    assert newcode and newcode != code

    # remove member (creator removes invitee)
    # find invitee id from members
    r = client.get(f'/api/teams/{team_id}/members', headers=headers1)
    members = r.get_json()['members']
    invitee = next((m for m in members if m['email']=='invitee@example.com'), None)
    assert invitee
    uid = invitee['id']
    r = client.delete(f'/api/teams/{team_id}/members/{uid}', headers=headers1)
    assert r.status_code == 200
