# Brevo email verification setup

The mobile registration flow is: registration form → email OTP → patient account creation → access activation. The backend creates a six-digit code; Brevo delivers it as a transactional email. Brevo does not generate the code.

1. In Brevo, create and verify a sender address under **Settings → Senders, Domains, IPs → Senders**. Authenticate a domain if you own one. Brevo's [sender guide](https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email) explains the verification step.
2. Create an API key in Brevo. Set `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and optionally `BREVO_SENDER_NAME` as backend environment variables. `BREVO_SENDER_EMAIL` must be the verified sender. Keep the key on the backend only; never put it in Flutter, the website, Git, or chat. Brevo's [transactional email API](https://developers.brevo.com/reference/send-transac-email) uses `POST /v3/smtp/email` with the `api-key` header.
3. Apply the additive Alembic migration `fe30b9a82104` to the intended development database after validating its target. Restart the backend so it reads the environment variables.
4. Register with an email inbox you control. The first request returns HTTP 202 and sends a code. A patient record does not exist yet. Enter the code on the mobile OTP screen. Successful verification returns HTTP 201, creates a patient, signs in, and opens the activation screen.

Codes expire after 10 minutes. Resend becomes available after 60 seconds, invalidates the old code, and is enforced by the backend. Five incorrect attempts invalidate a code until resend. The stored code is an HMAC digest; pending passwords are stored as Argon2 hashes. Neither the code nor API key is logged.

The backend returns HTTP 503 when Brevo is not configured or delivery fails. Live delivery requires a working Brevo account with transactional email enabled and available sending capacity.
