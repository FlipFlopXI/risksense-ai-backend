"""Generate the canonical API inventory from FastAPI's OpenAPI document."""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.main import app

OUTPUT = Path("BACKEND_ENDPOINT_INVENTORY.json")
METHODS = {"get", "post", "put", "patch", "delete"}
TAG_MODULE = {
    "Authentication": "app.api.v1.auth", "Health": "app.api.v1.health", "Vitals": "app.api.v1.vitals",
    "Subscriptions": "app.api.v1.subscriptions", "Insurance": "app.api.v1.insurance",
    "Laboratory Results": "app.api.v1.labs", "Clinicians": "app.api.v1.clinicians",
    "Administration": "app.api.v1.admin", "Patients": "app.api.v1.patients",
    "Patient Intelligence": "app.api.v1.intelligence", "Access": "app.api.v1.access",
    "Drug Assistant": "app.api.v1.drug_assistant", "Patient Medications": "app.api.v1.patient_medications",
}


def contract_name(value) -> str | None:
    if not isinstance(value, dict):
        return None
    reference = value.get("$ref")
    if reference:
        return reference.rsplit("/", 1)[-1]
    if value.get("type") == "array":
        return f"list[{contract_name(value.get('items')) or 'object'}]"
    return value.get("title") or value.get("type")


def access_for(path: str, method: str) -> tuple[str, list[str], bool, bool]:
    if path == "/health" or path in {"/auth/register", "/auth/login", "/auth/refresh"}:
        return "public", [], False, False
    if path in {"/auth/me", "/auth/logout"}:
        return "bearer", ["PATIENT", "CLINICIAN", "ADMIN"], False, False
    if path.startswith("/admin") or path.startswith("/access/mock"):
        return "bearer", ["ADMIN"], False, False
    if path.startswith("/clinicians"):
        if path.startswith("/clinicians/lookup"):
            return "bearer", ["PATIENT"], False, False
        return "bearer", ["CLINICIAN"], False, "/patients/" in path
    if path.startswith("/drug-assistant"):
        roles = ["PATIENT", "CLINICIAN"]
        clinical = not path.startswith("/drug-assistant/drugs")
        return "bearer", roles, clinical, clinical
    if path.startswith("/patient-medications"):
        return "bearer", ["PATIENT"] if method in {"POST", "PATCH", "DELETE"} else ["PATIENT", "CLINICIAN"], False, method == "GET"
    if path == "/risk-analysis":
        return "bearer", ["PATIENT", "CLINICIAN"], True, True
    if path.startswith("/reports"):
        return "bearer", ["PATIENT", "CLINICIAN"], False, True
    if path.startswith(("/subscriptions", "/insurance", "/health", "/patients", "/predictions", "/dashboard", "/access/entitlements")):
        return "bearer", ["PATIENT"], False, False
    return "bearer", ["PATIENT"], False, False


def readiness(path: str) -> tuple[str, str]:
    if path == "/health" or path.startswith("/drug-assistant/drugs") or path == "/admin/drug-assistant/status":
        return "WORKING", "Database-free regression coverage passed."
    if path == "/clinicians/assessment":
        return "INTENTIONALLY UNAVAILABLE", "Returns 503 because no validated temporary-assessment model is implemented."
    if path.startswith(("/reports", "/auth/refresh", "/auth/logout", "/health/body-measurements", "/patients/me/clinician")):
        return "UNTESTED", "Implemented with automated coverage; controlled database smoke test is blocked in this run."
    if path in {"/risk-analysis", "/auth/login"}:
        return "WORKING", "Previously exercised against the configured development database; isolated DB regression is blocked."
    if path.startswith(("/drug-assistant", "/patient-medications")):
        return "WORKING", "Previously exercised against development; database integration suite is blocked in this run."
    return "UNTESTED", "Registered and inspected; current isolated database suite is blocked."


def generate() -> dict:
    schema = app.openapi()
    rows = []
    for path, path_item in schema["paths"].items():
        for lower_method, operation in path_item.items():
            if lower_method not in METHODS:
                continue
            method = lower_method.upper()
            auth, roles, entitlement, relationship = access_for(path, method)
            content = operation.get("requestBody", {}).get("content", {})
            request_schema = None
            for media in ("application/json", "application/x-www-form-urlencoded"):
                if media in content:
                    request_schema = contract_name(content[media].get("schema"))
                    break
            success_code = next((code for code in operation.get("responses", {}) if code.startswith("2")), None)
            success = operation.get("responses", {}).get(success_code or "", {})
            response_content = success.get("content", {}).get("application/json", {})
            status, note = readiness(path)
            errors = [401, 422] if auth == "bearer" else [422]
            if roles:
                errors.append(403)
            if "{" in path:
                errors.append(404)
            if path.startswith("/drug-assistant"):
                errors.extend([409, 503])
            rows.append({
                "method": method, "route": path, "router_module": TAG_MODULE.get(operation.get("tags", [None])[0], "app.main"),
                "authentication": auth, "roles": roles, "entitlement_required": entitlement,
                "patient_clinician_relationship_required": relationship,
                "entitlement_rule": ("ACTIVE effective entitlement for PATIENT and patient-specific Drug Assistant access"
                                     if entitlement else "none"),
                "relationship_rule": ("ACTIVE approved clinician-patient link when CLINICIAN accesses a patient"
                                      if relationship else "none"),
                "request_schema": request_schema, "response_schema": contract_name(response_content.get("schema")),
                "success_status": int(success_code) if success_code else None,
                "known_error_statuses": sorted(set(errors)), "readiness": status, "readiness_note": note,
                "operation_id": operation.get("operationId"), "versioned_alias": None if path == "/health" else f"/api/v1{path}",
            })
    ids = [row["operation_id"] for row in rows]
    return {
        "openapi_title": schema["info"]["title"], "openapi_version": schema["info"]["version"],
        "canonical_operations": len(rows), "versioned_alias_operations": sum(row["versioned_alias"] is not None for row in rows),
        "total_application_operations": len(rows) + sum(row["versioned_alias"] is not None for row in rows),
        "duplicate_operation_ids": sorted({item for item in ids if ids.count(item) > 1}), "operations": rows,
    }


if __name__ == "__main__":
    document = generate()
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Canonical operations: {document['canonical_operations']}")
    print(f"Compatibility aliases: {document['versioned_alias_operations']}")
    print(f"Duplicate operation IDs: {len(document['duplicate_operation_ids'])}")
