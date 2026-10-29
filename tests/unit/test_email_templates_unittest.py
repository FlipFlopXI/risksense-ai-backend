"""Email rendering checks that do not require a database or live Brevo call."""

import re
import unittest
from unittest.mock import Mock, patch

from app.services.email_templates import (
    clinician_change_decision_email,
    recovery_code_email,
    registration_code_email,
    replacement_password_email,
)


class EmailTemplateTests(unittest.TestCase):
    def test_clinician_change_approval_shows_both_clinicians_and_escapes_html(self):
        message = clinician_change_decision_email(
            approved=True, patient_name="Alex", old_name="Dr Old <One>",
            old_institution="Old Clinic", old_id="RS-CLN-10001",
            new_name="Dr New", new_institution="New & Clinic", new_id="RS-CLN-10003",
        )
        self.assertIn("Dr Old <One>", message)
        self.assertIn("Dr New", message)
        self.assertIn("RS-CLN-10003", message)
        self.assertIn("Dr Old &lt;One&gt;", message.html)
        self.assertIn("New &amp; Clinic", message.html)
        self.assertNotIn("Dr Old <One>", message.html)
        self.assertIn("RiskSense AI", message.html)

    def test_clinician_change_rejection_keeps_current_link_message(self):
        message = clinician_change_decision_email(
            approved=False, patient_name="Alex", old_name="Dr Old",
            old_institution="Old Clinic", old_id="RS-CLN-10001",
            new_name="Dr New", new_institution="New Clinic", new_id="RS-CLN-10003",
        )
        self.assertIn("not approved", message)
        self.assertIn("current clinician remains linked", message)
        self.assertNotIn("Dr New", message.html)

    def test_otp_templates_have_centered_large_code_and_plain_text(self):
        for factory in (registration_code_email, recovery_code_email):
            with self.subTest(factory=factory.__name__):
                message = factory("042617")
                self.assertIn("\n\n042617\n\n", message)
                self.assertIn("042617", message.html)
                self.assertIn('align="center"', message.html)
                self.assertIn("font-size:36px", message.html)
                self.assertIn("10 minutes", message.html)
                self.assertIn("RiskSense AI", message.html)

    def test_replacement_password_is_prominent_and_html_escaped(self):
        message = replacement_password_email("Example123!<test>")
        self.assertIn("\n\nExample123!<test>\n\n", message)
        self.assertIn("Example123!&lt;test&gt;", message.html)
        self.assertNotIn("Example123!<test>", message.html)
        self.assertIn("font-size:25px", message.html)
        self.assertIn("Settings &gt; Change Password", message.html)
        self.assertRegex(message, re.compile(r"temporary RiskSense AI password is:\s+(\S+)"))

    def test_brevo_payload_contains_html_and_plain_text_without_live_send(self):
        from app.core.config import settings
        from app.services.registration_verification import send_transactional_email

        response = Mock()
        response.raise_for_status.return_value = None
        client = Mock()
        client.post.return_value = response
        context = Mock()
        context.__enter__ = Mock(return_value=client)
        context.__exit__ = Mock(return_value=False)
        with (patch.object(settings, "BREVO_API_KEY", "unit-test-key"),
              patch.object(settings, "BREVO_SENDER_EMAIL", "sender@example.test"),
              patch("app.services.registration_verification.httpx.Client", return_value=context)):
            send_transactional_email("recipient@example.test", "Test", registration_code_email("123456"))

        payload = client.post.call_args.kwargs["json"]
        self.assertIn("123456", payload["textContent"])
        self.assertIn("123456", payload["htmlContent"])
        self.assertEqual(payload["to"], [{"email": "recipient@example.test"}])


if __name__ == "__main__":
    unittest.main()
