from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.auth import PasswordChangeRequest
from app.services import session_service


def test_password_change_uses_registration_strength_policy():
    request = PasswordChangeRequest(current_password="Old123!", new_password="New123!")
    assert request.new_password == "New123!"
    for weak in ("short", "alllowercase123!", "NoNumber!", "NoSpecial123"):
        with pytest.raises(ValidationError):
            PasswordChangeRequest(current_password="Old123!", new_password=weak)


def test_password_change_rejects_wrong_or_unchanged_password(monkeypatch):
    user = SimpleNamespace(id=uuid4(), password_hash="stored")
    db = SimpleNamespace()
    monkeypatch.setattr(session_service, "verify_password",
                        lambda supplied, stored: supplied == "Old123!")
    with pytest.raises(session_service.PasswordRejected):
        session_service.change_password(db, user, "wrong", "New123!", None)
    with pytest.raises(session_service.PasswordRejected):
        session_service.change_password(db, user, "Old123!", "Old123!", None)
    assert user.password_hash == "stored"


def test_password_change_revokes_other_sessions_without_auditing_secrets(monkeypatch):
    user = SimpleNamespace(id=uuid4(), password_hash="stored")
    current_session = uuid4()
    recorded = []

    class Db:
        def execute(self, statement):
            recorded.append(str(statement))

        def commit(self):
            recorded.append("commit")

    monkeypatch.setattr(session_service, "verify_password",
                        lambda supplied, stored: supplied == "Old123!")
    monkeypatch.setattr(session_service, "hash_password",
                        lambda supplied: "new-hash")
    monkeypatch.setattr(session_service, "add_audit_event",
                        lambda db, action, **kwargs: recorded.append((action, kwargs)))

    session_service.change_password(Db(), user, "Old123!", "New123!", current_session)
    assert user.password_hash == "new-hash"
    assert any("auth_sessions.id !=" in item for item in recorded if isinstance(item, str))
    assert recorded[-1] == "commit"
    assert not any("Old123!" in str(item) or "New123!" in str(item) for item in recorded)


def test_session_revocation_scopes_lookup_to_current_user():
    user = SimpleNamespace(id=uuid4())

    class Db:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

        def commit(self):
            raise AssertionError("Unknown session must not be committed")

    db = Db()
    assert session_service.revoke_session_by_id(db, user, uuid4()) is False
    sql = str(db.statement)
    assert "auth_sessions.user_id" in sql
    assert "auth_sessions.revoked_at IS NULL" in sql
