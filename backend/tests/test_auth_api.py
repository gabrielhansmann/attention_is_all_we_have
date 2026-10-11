"""Sign-in, sessions, lockout and sign-out against the real database, inside a transaction that is rolled back."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conn
from app.auth import passwords, service
from app.main import app

pytestmark = pytest.mark.real_auth
PASSWORD = "a long enough passphrase"


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(passwords, "N", 2**10)           # fast hashes; the stored parameters stay self-describing
    app.dependency_overrides[get_conn] = lambda: db
    c = TestClient(app)
    c.db = db
    c.user = service.create_user(db, "Pat.Manager@Example.com", "Pat Manager", PASSWORD)
    yield c
    app.dependency_overrides.clear()


def login(client, email="pat.manager@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_a_token_that_works_and_exposes_no_secrets(client):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {"id": str(client.user["id"]), "email": "pat.manager@example.com",
                            "display_name": "Pat Manager", "role": "pm"}
    assert "password" not in r.text and "scrypt" not in r.text
    me = client.get("/api/auth/me", headers=bearer(body["token"]))
    assert me.status_code == 200 and me.json()["email"] == "pat.manager@example.com"
    assert client.get("/api/agents", headers=bearer(body["token"])).status_code == 200


def test_only_a_hash_of_the_token_is_stored(client):
    token = login(client).json()["token"]
    rows = client.db.execute("select token_hash from public.auth_session where user_id=%s",(client.user['id'],)).fetchall()
    assert [r["token_hash"] for r in rows] == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in rows[0]["token_hash"]


def test_email_is_not_case_sensitive(client):
    assert login(client, email="  PAT.MANAGER@example.COM ").status_code == 200


def test_every_login_failure_looks_the_same(client):
    wrong = login(client, password="not the passphrase")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "invalid email or password"}


def test_an_inactive_account_cannot_sign_in_and_looks_like_a_wrong_password(client):
    service.set_active(client.db, "pat.manager@example.com", False)
    r = login(client)
    assert r.status_code == 401 and r.json() == {"detail": "invalid email or password"}


def test_five_wrong_passwords_lock_the_account_even_for_the_right_one(client):
    for _ in range(service.MAX_FAILED):
        assert login(client, password="wrong wrong wrong").status_code == 401
    locked = login(client)                                  # correct password, still refused
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
    # time passes
    client.db.execute("update public.app_user set locked_until = now() - interval '1 minute' where email = %s",
                      ("pat.manager@example.com",))
    assert login(client).status_code == 200
    assert client.db.execute("select failed_attempts, locked_until from public.app_user where email = %s",
                             ("pat.manager@example.com",)).fetchone() == {"failed_attempts": 0, "locked_until": None}


def test_logout_revokes_only_that_session(client):
    t1, t2 = login(client).json()["token"], login(client).json()["token"]
    assert client.post("/api/auth/logout", headers=bearer(t1)).status_code == 204
    assert client.get("/api/auth/me", headers=bearer(t1)).status_code == 401
    assert client.get("/api/auth/me", headers=bearer(t2)).status_code == 200


@pytest.mark.parametrize("break_it", [
    "update public.auth_session set expires_at = now() - interval '1 second'",
    "update public.auth_session set revoked_at = now()",
    "update public.app_user set active = false",
])
def test_expired_revoked_and_deactivated_sessions_are_refused_with_the_same_message(client, break_it):
    token = login(client).json()["token"]
    client.db.execute(break_it)
    r = client.get("/api/auth/me", headers=bearer(token))
    assert r.status_code == 401 and r.json() == {"detail": "not authenticated"}


def test_a_guessed_token_is_refused(client):
    login(client)
    assert client.get("/api/auth/me", headers=bearer("x" * 43)).status_code == 401


def test_changing_the_password_signs_everyone_out(client):
    token = login(client).json()["token"]
    service.set_password(client.db, "pat.manager@example.com", "a brand new passphrase")
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401
    assert login(client).status_code == 401
    assert login(client, password="a brand new passphrase").status_code == 200


def test_user_creation_rules(client):
    with pytest.raises(ValueError, match="already exists"):
        service.create_user(client.db, "PAT.MANAGER@example.com", "Again", PASSWORD)
    with pytest.raises(ValueError, match="at least 12"):
        service.create_user(client.db, "new@example.com", "New", "short")
    with pytest.raises(ValueError, match="email"):
        service.create_user(client.db, "not-an-email", "New", PASSWORD)
    with pytest.raises(ValueError, match="role"):
        service.create_user(client.db, "new@example.com", "New", PASSWORD, role="root")
    assert [u["email"] for u in service.list_users(client.db) if u["email"] == "pat.manager@example.com"]


def test_session_lifetime_follows_the_setting(client, monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_HOURS", "2")
    expires = datetime.fromisoformat(login(client).json()["expires_at"])
    assert timedelta(hours=1, minutes=59) < expires - datetime.now(timezone.utc) < timedelta(hours=2, minutes=1)


def test_the_password_hash_is_never_in_any_response(client):
    token = login(client).json()["token"]
    assert "scrypt" not in client.get("/api/auth/me", headers=bearer(token)).text
