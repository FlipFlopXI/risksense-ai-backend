from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.dependencies import get_database, require_role
from app.models.user import User, UserRole
from app.schemas.users import PatientResponse, PatientUpdateRequest
from app.services.health_service import get_patient_by_user_id
from app.models.patient_clinician import PatientClinician, PatientClinicianStatus
from app.models.clinician import Clinician, ClinicianApprovalStatus
from app.schemas.access import MyClinicianResponse
from app.schemas.onboarding import OnboardingContext, OnboardingDetails, OnboardingResult
from app.models.health_profile import HealthProfile
from app.models.body_measurement import BodyMeasurement
from app.services.audit_service import add_audit_event
from app.services.entitlement_service import get_effective_entitlement
from app.services.patient_clinician_service import get_patient_clinician
from app.services.clinician_service import get_approved_clinician
from app.services import clinician_change_service
from app.schemas.clinician_change import ClinicianChangeCreate, ClinicianChangeResponse, ClinicianIdentity
from app.schemas.notification_preferences import NotificationPreferencesResponse, NotificationPreferencesUpdate
from app.services.risk_result_notification_service import (
    ResultEmailUnavailable, email_enabled, set_email_enabled,
)
from datetime import datetime, timezone

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/clinicians/lookup/{risk_sense_id}", response_model=ClinicianIdentity)
def lookup_replacement_clinician(risk_sense_id: str,
        user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    clinician = get_approved_clinician(db, risk_sense_id.strip())
    if clinician is None:
        raise HTTPException(status_code=404, detail="Approved clinician not found.")
    return clinician_change_service.identity(clinician)


@router.get("/me/clinician-change-request", response_model=ClinicianChangeResponse)
def my_pending_clinician_change(user: User = Depends(require_role(UserRole.PATIENT)),
                                db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    row = clinician_change_service.pending_for_patient(db, patient.id)
    if row is None:
        raise HTTPException(status_code=404, detail="No pending clinician change request.")
    return clinician_change_service.response(db, row)


@router.post("/me/clinician-change-request", response_model=ClinicianChangeResponse, status_code=201)
def request_clinician_change(request: ClinicianChangeCreate,
        user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    row = clinician_change_service.request_change(db, patient, user.id, request.risk_sense_id)
    return clinician_change_service.response(db, row)


@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
def notification_preferences(user: User = Depends(require_role(UserRole.PATIENT)),
                             db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return NotificationPreferencesResponse(email_elevated_results=email_enabled(db, patient.id))


@router.patch("/notification-preferences", response_model=NotificationPreferencesResponse)
def update_notification_preferences(request: NotificationPreferencesUpdate,
                                    user: User = Depends(require_role(UserRole.PATIENT)),
                                    db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    try:
        enabled = set_email_enabled(db, patient.id, user.id, request.email_elevated_results)
    except ResultEmailUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return NotificationPreferencesResponse(email_elevated_results=enabled)


def onboarding_complete(profile: HealthProfile | None) -> bool:
    return bool(profile and profile.height_cm and profile.weight_kg and
                profile.smoking_status and profile.activity_level and profile.alcohol_status)


@router.get("/onboarding", response_model=OnboardingContext)
def onboarding_context(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id))
    fields = OnboardingDetails.model_fields
    existing = {key: getattr(profile, key, None) for key in fields
                if key not in {"ethnicity", "has_chronic_condition", "chronic_conditions", "chronic_medications"}} if profile else {}
    existing.update({"ethnicity": patient.ethnicity,
                     "has_chronic_condition": bool(profile and profile.existing_conditions),
                     "chronic_conditions": profile.existing_conditions if profile else None,
                     "chronic_medications": profile.current_medications if profile else None})
    return OnboardingContext(completed=onboarding_complete(profile), existing=existing)


@router.post("/onboarding", response_model=OnboardingResult)
def save_onboarding(request: OnboardingDetails, user: User = Depends(require_role(UserRole.PATIENT)),
                    db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    entitlement = get_effective_entitlement(db, patient.id)
    link = get_patient_clinician(db, patient.id, entitlement.clinician_id) if entitlement else None
    if not entitlement or not link or link.status != PatientClinicianStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Active access and a clinician link are required.")
    profile = db.scalar(select(HealthProfile).where(HealthProfile.patient_id == patient.id).with_for_update())
    created = profile is None
    if created:
        profile = HealthProfile(patient_id=patient.id)
        db.add(profile)
    if patient.ethnicity is None and request.ethnicity:
        patient.ethnicity = request.ethnicity
    for key in ("height_cm", "weight_kg", "waist_circumference_cm", "smoking_status", "activity_level", "alcohol_status",
                "family_history_diabetes", "family_history_heart_disease", "family_history_hypertension"):
        setattr(profile, key, getattr(request, key))
    if request.has_chronic_condition:
        profile.existing_conditions = request.chronic_conditions
        profile.current_medications = request.chronic_medications
    db.flush()
    db.add(BodyMeasurement(patient_id=patient.id, height_cm=request.height_cm, weight_kg=request.weight_kg,
                           waist_circumference_cm=request.waist_circumference_cm, source="health_profile",
                           measured_at=datetime.now(timezone.utc)))
    add_audit_event(db, "HEALTH_PROFILE_CREATED" if created else "HEALTH_PROFILE_UPDATED",
                    user_id=patient.user_id, resource_type="health_profile", resource_id=str(profile.id))
    add_audit_event(db, "PATIENT_ONBOARDING_COMPLETED", user_id=patient.user_id,
                    resource_type="patient", resource_id=str(patient.id))
    db.commit()
    return OnboardingResult(saved=True)


@router.get("/me", response_model=PatientResponse)
def me(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return patient


@router.patch("/me", response_model=PatientResponse)
def update_me(request: PatientUpdateRequest, user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    for field, value in request.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/me/clinician", response_model=MyClinicianResponse)
def my_clinician(user: User = Depends(require_role(UserRole.PATIENT)), db: Session = Depends(get_database)):
    patient = get_patient_by_user_id(db, user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    row = db.execute(select(PatientClinician, Clinician).join(
        Clinician, Clinician.id == PatientClinician.clinician_id
    ).where(PatientClinician.patient_id == patient.id,
            PatientClinician.status == PatientClinicianStatus.ACTIVE,
            Clinician.approval_status == ClinicianApprovalStatus.APPROVED)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Active clinician relationship not found.")
    link, clinician = row
    return MyClinicianResponse(
        relationship_id=link.id, relationship_status=link.status, linked_at=link.linked_at,
        risk_sense_id=clinician.risk_sense_id,
        display_name=f"{clinician.first_name} {clinician.last_name}",
        professional_title=clinician.professional_title, specialization=clinician.specialization,
        institution=clinician.institution,
    )
