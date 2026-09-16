import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinician import Clinician, ClinicianApprovalStatus


def get_clinician_by_risk_sense_id(db: Session, risk_sense_id: str) -> Clinician | None:
    return db.scalar(select(Clinician).where(Clinician.risk_sense_id == risk_sense_id.upper()))


def get_approved_clinician(db: Session, risk_sense_id: str) -> Clinician | None:
    return db.scalar(
        select(Clinician)
        .join(Clinician.user)
        .where(
            Clinician.risk_sense_id == risk_sense_id.upper(),
            Clinician.approval_status == ClinicianApprovalStatus.APPROVED,
        )
        .where(Clinician.user.has(is_active=True))
    )


def generate_risk_sense_id(db: Session) -> str:
    for _ in range(100):
        value = f"RS-CLN-{secrets.randbelow(100000):05d}"
        if get_clinician_by_risk_sense_id(db, value) is None:
            return value
    raise RuntimeError("Unable to allocate a unique RiskSense clinician identifier.")
