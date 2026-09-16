from app.models.clinician import ClinicianApprovalStatus
from app.models.patient_clinician import PatientClinicianStatus


def test_approved_lifecycle_values():
    assert {item.value for item in ClinicianApprovalStatus} == {"pending", "approved", "suspended", "rejected"}
    assert {item.value for item in PatientClinicianStatus} == {"active", "inactive"}
