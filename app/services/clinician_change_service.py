"""Admin-reviewed replacement of a patient's linked clinician."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.access_entitlement import AccessEntitlement, EntitlementStatus
from app.models.clinician import Clinician
from app.models.clinician_change_request import ClinicianChangeRequest, ClinicianChangeStatus
from app.models.patient import Patient
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.subscription import Subscription
from app.models.insurance import Insurance
from app.models.user import User
from app.schemas.clinician_change import ClinicianChangeResponse, ClinicianIdentity
from app.services.audit_service import add_audit_event
from app.services.email_templates import clinician_change_decision_email
from app.services.registration_verification import send_transactional_email
from app.services.clinician_service import get_approved_clinician
from app.services.entitlement_service import get_effective_entitlement
from app.services.patient_clinician_service import get_patient_clinician, link_patient_clinician, unlink_patient_clinician

logger = logging.getLogger(__name__)


def _notify_decision(db: Session, row: ClinicianChangeRequest) -> None:
    """Send only after the reviewed decision commits; delivery cannot undo access changes."""
    try:
        patient = db.get(Patient, row.patient_id)
        user = db.get(User, patient.user_id)
        old = db.get(Clinician, row.old_clinician_id)
        new = db.get(Clinician, row.new_clinician_id)
        approved = row.status == ClinicianChangeStatus.APPROVED
        content = clinician_change_decision_email(
            approved=approved, patient_name=patient.first_name,
            old_name=f"{old.first_name} {old.last_name}", old_institution=old.institution,
            old_id=old.risk_sense_id,
            new_name=f"{new.first_name} {new.last_name}", new_institution=new.institution,
            new_id=new.risk_sense_id,
        )
        subject = ("Your RiskSense AI clinician change was approved" if approved
                   else "Your RiskSense AI clinician change request")
        send_transactional_email(user.email, subject, content)
        add_audit_event(db, "CLINICIAN_CHANGE_EMAIL_SENT", user_id=patient.user_id,
                        resource_type="clinician_change_request", resource_id=str(row.id))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Clinician change email delivery failed for request %s (%s)",
                       row.id, type(exc).__name__)
        try:
            add_audit_event(db, "CLINICIAN_CHANGE_EMAIL_FAILED",
                            resource_type="clinician_change_request", resource_id=str(row.id), status="failure")
            db.commit()
        except Exception:
            db.rollback()


def identity(clinician: Clinician) -> ClinicianIdentity:
    return ClinicianIdentity(risk_sense_id=clinician.risk_sense_id,
                             display_name=f"{clinician.first_name} {clinician.last_name}",
                             institution=clinician.institution)


def response(db: Session, row: ClinicianChangeRequest) -> ClinicianChangeResponse:
    patient = db.get(Patient, row.patient_id)
    old = db.get(Clinician, row.old_clinician_id)
    new = db.get(Clinician, row.new_clinician_id)
    status = row.status.value if isinstance(row.status, ClinicianChangeStatus) else str(row.status)
    return ClinicianChangeResponse(id=row.id, status=status,
        created_at=row.created_at, patient_id=row.patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_email=db.get(User, patient.user_id).email,
        old_clinician=identity(old), new_clinician=identity(new))


def pending_for_patient(db: Session, patient_id: UUID) -> ClinicianChangeRequest | None:
    return db.scalar(select(ClinicianChangeRequest).where(
        ClinicianChangeRequest.patient_id == patient_id,
        ClinicianChangeRequest.status == ClinicianChangeStatus.PENDING))


def request_change(db: Session, patient: Patient, actor_id: UUID,
                   risk_sense_id: str) -> ClinicianChangeRequest:
    # The patient row serializes competing requests; the partial unique index is
    # the final protection against duplicate pending requests.
    db.scalar(select(Patient.id).where(Patient.id == patient.id).with_for_update())
    entitlement = get_effective_entitlement(db, patient.id)
    if entitlement is None or entitlement.clinician_id is None:
        raise HTTPException(403, "Active access with a linked clinician is required.")
    old_link = get_patient_clinician(db, patient.id, entitlement.clinician_id)
    if old_link is None or old_link.status != PatientClinicianStatus.ACTIVE:
        raise HTTPException(409, "The current clinician link is no longer active.")
    clinician = get_approved_clinician(db, risk_sense_id)
    if clinician is None:
        raise HTTPException(404, "Approved clinician not found.")
    if clinician.id == entitlement.clinician_id:
        raise HTTPException(409, "This clinician is already linked to your account.")
    if pending_for_patient(db, patient.id) is not None:
        raise HTTPException(409, "A clinician change request is already pending.")
    row = ClinicianChangeRequest(patient_id=patient.id,
        old_clinician_id=entitlement.clinician_id, new_clinician_id=clinician.id)
    db.add(row)
    try:
        db.flush()
        add_audit_event(db, "CLINICIAN_CHANGE_REQUESTED", user_id=actor_id,
                        resource_type="clinician_change_request", resource_id=str(row.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A clinician change request is already pending.") from None
    db.refresh(row)
    return row


def pending_requests(db: Session) -> list[ClinicianChangeRequest]:
    return list(db.scalars(select(ClinicianChangeRequest).where(
        ClinicianChangeRequest.status == ClinicianChangeStatus.PENDING
    ).order_by(ClinicianChangeRequest.created_at.desc(), ClinicianChangeRequest.id.desc())).all())


def decide(db: Session, request_id: UUID, admin_id: UUID,
           decision: str) -> ClinicianChangeRequest:
    row = db.scalar(select(ClinicianChangeRequest).where(
        ClinicianChangeRequest.id == request_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Clinician change request not found.")
    if row.status != ClinicianChangeStatus.PENDING:
        raise HTTPException(409, "This request has already been reviewed.")
    db.scalar(select(Patient.id).where(Patient.id == row.patient_id).with_for_update())
    if decision == "approve":
        new = db.get(Clinician, row.new_clinician_id)
        if new is None or get_approved_clinician(db, new.risk_sense_id) is None:
            raise HTTPException(409, "The requested clinician is no longer available.")
        effective = get_effective_entitlement(db, row.patient_id)
        if effective is None or effective.clinician_id != row.old_clinician_id:
            raise HTTPException(409, "The patient's active access or clinician has changed.")
        links = list(db.scalars(select(PatientClinician).where(
            PatientClinician.patient_id == row.patient_id,
            PatientClinician.status == PatientClinicianStatus.ACTIVE).with_for_update()).all())
        if not any(link.clinician_id == row.old_clinician_id for link in links):
            raise HTTPException(409, "The original clinician link is no longer active.")
        entitlements = list(db.scalars(select(AccessEntitlement).where(
            AccessEntitlement.patient_id == row.patient_id,
            AccessEntitlement.status == EntitlementStatus.ACTIVE).with_for_update()).all())
        if any(item.clinician_id != row.old_clinician_id for item in entitlements):
            raise HTTPException(409, "The patient's entitlements have changed. Review access before approving.")
        for link in links:
            unlink_patient_clinician(db, link, admin_id)
        link_patient_clinician(db, row.patient_id, row.new_clinician_id, admin_id)
        for item in entitlements:
            item.clinician_id = row.new_clinician_id
        # Staged renewals and insurance verification read these identifiers.
        # Keep them aligned so later activation cannot restore the old link.
        old_clinician = db.get(Clinician, row.old_clinician_id)
        subscription = db.scalar(select(Subscription).where(Subscription.patient_id == row.patient_id).with_for_update())
        if subscription and old_clinician and subscription.requested_clinician_risk_sense_id == old_clinician.risk_sense_id:
            subscription.requested_clinician_risk_sense_id = new.risk_sense_id
        insurance = db.scalar(select(Insurance).where(Insurance.patient_id == row.patient_id).with_for_update())
        if insurance and old_clinician and insurance.requested_clinician_risk_sense_id == old_clinician.risk_sense_id:
            insurance.requested_clinician_risk_sense_id = new.risk_sense_id
        row.status = ClinicianChangeStatus.APPROVED
    elif decision == "reject":
        row.status = ClinicianChangeStatus.REJECTED
    else:
        raise ValueError("Unsupported clinician change decision.")
    row.reviewed_by_admin_id = admin_id
    row.reviewed_at = datetime.now(timezone.utc)
    add_audit_event(db, "CLINICIAN_CHANGE_APPROVED" if decision == "approve" else "CLINICIAN_CHANGE_REJECTED",
                    user_id=admin_id, resource_type="clinician_change_request", resource_id=str(row.id))
    db.commit()
    db.refresh(row)
    _notify_decision(db, row)
    return row
