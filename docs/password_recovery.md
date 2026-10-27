# Password recovery

The mobile login screen opens a rounded recovery dialog. The user enters their registered email, receives a six-digit code through the existing Brevo transactional email configuration, and enters it before tapping **Generate Password**. The backend then emails a replacement password to the registered address. The response never contains the password.

The password includes a short fragment of the account holder's name, twelve cryptographically random letters/digits, four random digits, and a special character. It is stored only as an Argon2 password hash. The user can sign in with it and choose a new password in **Settings → Change Password**.

Codes expire after 10 minutes. Requests are limited to one per account per minute, and a new code invalidates the previous one. Five incorrect codes invalidate a challenge. Starting recovery returns the same generic response for unknown and known addresses. An incorrect or expired code cannot change the account. Existing refresh-backed sessions are revoked when the replacement is committed; current access tokens tied to those sessions are also rejected by `get_current_user`.

The backend uses the existing `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and optional `BREVO_SENDER_NAME` variables. **No additional Brevo key is needed.** Do not put the key in Flutter or commit it. The additive migration is `f851c4d3a920`.

Sending a password through email is less private than a reset link. This implementation follows the requested demonstration behavior. Users should change the emailed password in Settings after signing in.
