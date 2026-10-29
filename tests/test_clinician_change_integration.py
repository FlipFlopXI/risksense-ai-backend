"""Database-backed authorization and atomic clinician replacement checks."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.access_entitlement import AccessEntitlement
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.models.clinician_change_request import ClinicianChangeRequest
from app.models.patient import Patient
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.verification_service import staged_activate_subscription


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


def _user(db, email, role):
    user = User(email=email, role=role, is_active=True,
                password_hash=hash_password("SafeTestPassword123!"))
    db.add(user)
    db.flush()
    return user


def _clinician(db, email, code):
    user = _user(db, email, UserRole.CLINICIAN)
    clinician = Clinician(user_id=user.id, risk_sense_id=code,
        approval_status=ClinicianApprovalStatus.APPROVED, approved_at=datetime.now(timezone.utc),
        first_name="Test", last_name=code[-5:], institution="Test Clinic")
    db.add(clinician)
    db.flush()
    return clinician


def test_change_requires_admin_and_replaces_link_and_entitlement(client, db, monkeypatch):
    from app.services import clinician_change_service
    sent = []
    monkeypatch.setattr(clinician_change_service, "send_transactional_email",
                        lambda email, subject, content: sent.append((email, subject, content)))
    patient_user = _user(db, "change.patient@example.test", UserRole.PATIENT)
    patient = Patient(user_id=patient_user.id, first_name="Change", last_name="Patient")
    db.add(patient)
    db.flush()
    admin = _user(db, "change.admin@example.test", UserRole.ADMIN)
    old = _clinician(db, "old.change@example.test", "RS-CLN-72001")
    new = _clinician(db, "new.change@example.test", "RS-CLN-72002")
    subscription = Subscription(patient_id=patient.id, plan="premium", status=SubscriptionStatus.PENDING,
                                requested_clinician_risk_sense_id=old.risk_sense_id)
    db.add(subscription)
    db.commit()
    entitlement = staged_activate_subscription(db, patient, subscription, old.risk_sense_id, admin.id)

    lookup = client.get(f"/patients/clinicians/lookup/{new.risk_sense_id}", headers=_headers(patient_user))
    assert lookup.status_code == 200
    assert lookup.json()["institution"] == "Test Clinic"
    requested = client.post("/patients/me/clinician-change-request", headers=_headers(patient_user),
                            json={"risk_sense_id": new.risk_sense_id})
    assert requested.status_code == 201
    request_id = requested.json()["id"]
    assert requested.json()["status"] == "pending"
    assert client.post("/patients/me/clinician-change-request", headers=_headers(patient_user),
                       json={"risk_sense_id": new.risk_sense_id}).status_code == 409
    assert client.get("/admin/clinician-change-requests", headers=_headers(patient_user)).status_code == 403
    assert client.post(f"/admin/clinician-change-requests/{request_id}/decision",
                       headers=_headers(patient_user), json={"decision": "approve"}).status_code == 403
    assert db.get(AccessEntitlement, entitlement.id).clinician_id == old.id

    pending = client.get("/admin/clinician-change-requests", headers=_headers(admin))
    assert pending.status_code == 200 and len(pending.json()) == 1
    approved = client.post(f"/admin/clinician-change-requests/{request_id}/decision",
                           headers=_headers(admin), json={"decision": "approve"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert len(sent) == 1 and sent[0][0] == patient_user.email
    assert "approved" in sent[0][1]
    assert old.risk_sense_id in sent[0][2] and new.risk_sense_id in sent[0][2]
    db.expire_all()
    assert db.get(AccessEntitlement, entitlement.id).clinician_id == new.id
    assert db.get(Subscription, subscription.id).requested_clinician_risk_sense_id == new.risk_sense_id
    links = list(db.scalars(select(PatientClinician).where(PatientClinician.patient_id == patient.id)).all())
    assert {link.clinician_id for link in links if link.status == PatientClinicianStatus.ACTIVE} == {new.id}
    assert client.get("/admin/clinician-change-requests", headers=_headers(admin)).json() == []
    assert client.post(f"/admin/clinician-change-requests/{request_id}/decision",
                       headers=_headers(admin), json={"decision": "approve"}).status_code == 409


def test_rejection_keeps_current_link_and_entitlement(client, db, monkeypatch):
    from app.services import clinician_change_service
    sent = []
    monkeypatch.setattr(clinician_change_service, "send_transactional_email",
                        lambda email, subject, content: sent.append((email, subject, content)))
    patient_user = _user(db, "reject.patient@example.test", UserRole.PATIENT)
    patient = Patient(user_id=patient_user.id, first_name="Reject", last_name="Patient")
    db.add(patient)
    db.flush()
    admin = _user(db, "reject.admin@example.test", UserRole.ADMIN)
    old = _clinician(db, "old.reject@example.test", "RS-CLN-72003")
    new = _clinician(db, "new.reject@example.test", "RS-CLN-72004")
    subscription = Subscription(patient_id=patient.id, plan="premium", status=SubscriptionStatus.PENDING,
                                requested_clinician_risk_sense_id=old.risk_sense_id)
    db.add(subscription)
    db.commit()
    entitlement = staged_activate_subscription(db, patient, subscription, old.risk_sense_id, admin.id)
    requested = client.post("/patients/me/clinician-change-request", headers=_headers(patient_user),
                            json={"risk_sense_id": new.risk_sense_id})
    assert requested.status_code == 201
    decision = client.post(f"/admin/clinician-change-requests/{requested.json()['id']}/decision",
                           headers=_headers(admin), json={"decision": "reject"})
    assert decision.status_code == 200 and decision.json()["status"] == "rejected"
    assert len(sent) == 1 and sent[0][0] == patient_user.email
    assert "not approved" in sent[0][2]
    db.expire_all()
    assert db.get(AccessEntitlement, entitlement.id).clinician_id == old.id
    assert db.get(Subscription, subscription.id).requested_clinician_risk_sense_id == old.risk_sense_id
    assert db.scalar(select(ClinicianChangeRequest).where(
        ClinicianChangeRequest.patient_id == patient.id)).status == "rejected"
