import unittest

from pydantic import ValidationError

from app.schemas.clinician_change import ClinicianChangeCreate, ClinicianChangeDecision


class ClinicianChangeContractTests(unittest.TestCase):
    def test_risk_sense_identifier_must_have_exact_format(self):
        self.assertEqual(ClinicianChangeCreate(risk_sense_id="RS-CLN-12345").risk_sense_id,
                         "RS-CLN-12345")
        for value in ("RS-CLN-1234", "RS-CLN-123456", "RS-CLN-abcde", "12345"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ClinicianChangeCreate(risk_sense_id=value)

    def test_only_approve_or_reject_decisions_are_accepted(self):
        for value in ("approve", "reject"):
            self.assertEqual(ClinicianChangeDecision(decision=value).decision, value)
        for value in ("pending", "activate", "", "APPROVE"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ClinicianChangeDecision(decision=value)


if __name__ == "__main__":
    unittest.main()
