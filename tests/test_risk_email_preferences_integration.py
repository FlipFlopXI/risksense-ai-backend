"""Database-backed ownership and opt-in checks for result email preferences."""

from sqlalchemy import select

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.patient_notification_preference import PatientNotificationPreference
from app.models.user import UserRole
from test_security_integration import _auth, _patient, _token, _user


def test_patient_owns_email_preference_and_default_is_off(client, db, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "integration-test-only-key")
    monkeypatch.setattr(settings, "BREVO_SENDER_EMAIL", "sender@example.test")
    first_user, first = _patient(db, "risk.email.first@example.test")
    second_user, second = _patient(db, "risk.email.second@example.test")
    admin = _user(db, UserRole.ADMIN, "risk.email.admin@example.test")
    db.commit()
    path = "/api/v1/patients/notification-preferences"

    assert client.get(path, headers=_auth(_token(first_user))).json() == {
        "email_elevated_results": False,
    }
    assert db.get(PatientNotificationPreference, first.id) is None
    assert client.patch(path, headers=_auth(_token(admin)),
                        json={"email_elevated_results": True}).status_code == 403
    assert client.patch(path, headers=_auth(_token(first_user)),
                        json={"email_elevated_results": "yes"}).status_code == 422

    updated = client.patch(path, headers=_auth(_token(first_user)),
                           json={"email_elevated_results": True})
    assert updated.status_code == 200
    assert updated.json() == {"email_elevated_results": True}
    assert client.get(path, headers=_auth(_token(second_user))).json() == {
        "email_elevated_results": False,
    }
    assert db.get(PatientNotificationPreference, second.id) is None
    assert db.get(PatientNotificationPreference, first.id).email_elevated_results is True
    assert db.scalar(select(AuditLog).where(
        AuditLog.action == "RISK_RESULT_EMAIL_PREFERENCE_UPDATED",
        AuditLog.user_id == first_user.id,
    )) is not None

    disabled = client.patch(path, headers=_auth(_token(first_user)),
                            json={"email_elevated_results": False})
    assert disabled.status_code == 200
    assert disabled.json() == {"email_elevated_results": False}
