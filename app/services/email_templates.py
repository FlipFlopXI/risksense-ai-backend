"""Accessible text and responsive HTML for transactional account emails."""

from html import escape


class EmailContent(str):
    """Plain-text body with an HTML alternative for email clients that support it."""

    def __new__(cls, text: str, html: str) -> "EmailContent":
        value = super().__new__(cls, text)
        value.html = html
        return value


def _layout(*, title: str, introduction: str, value: str, label: str,
            explanation: str, footer: str, is_code: bool) -> str:
    safe_title = escape(title)
    safe_intro = escape(introduction)
    safe_value = escape(value)
    safe_label = escape(label)
    safe_explanation = escape(explanation)
    safe_footer = escape(footer)
    value_style = (
        "font-size:36px;letter-spacing:0.22em;" if is_code
        else "font-size:25px;letter-spacing:0.02em;overflow-wrap:anywhere;word-break:break-word;"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>@media screen and (max-width:420px){{.code-value{{font-size:29px!important;letter-spacing:0.1em!important;}}}}</style>
<title>{safe_title}</title></head>
<body style="margin:0;padding:0;background:#edf4fa;color:#102244;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{safe_title}</div>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#edf4fa;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;background:#ffffff;border:1px solid #d5e6f2;border-radius:20px;overflow:hidden;">
<tr><td style="padding:25px 30px;background:#061b43;color:#ffffff;font-size:21px;font-weight:700;letter-spacing:0.02em;">RiskSense <span style="color:#83d5ef;">AI</span></td></tr>
<tr><td style="padding:30px 30px 10px;">
<h1 style="margin:0 0 16px;font-size:25px;line-height:1.25;color:#102244;">{safe_title}</h1>
<p style="margin:0;color:#425672;font-size:16px;line-height:1.55;">{safe_intro}</p>
</td></tr>
<tr><td style="padding:22px 30px;">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#eef8fc;border:1px solid #c8e8f3;border-radius:16px;">
<tr><td align="center" style="padding:22px 14px 24px;">
<p style="margin:0 0 12px;color:#52667c;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">{safe_label}</p>
<div class="{'code-value' if is_code else 'password-value'}" style="margin:0 auto;color:#08255b;font-family:Arial,Helvetica,sans-serif;font-weight:800;line-height:1.3;{value_style}">{safe_value}</div>
</td></tr></table></td></tr>
<tr><td style="padding:0 30px 28px;">
<p style="margin:0;color:#425672;font-size:15px;line-height:1.6;">{safe_explanation}</p>
<p style="margin:22px 0 0;padding-top:18px;border-top:1px solid #e4ecf4;color:#68788d;font-size:13px;line-height:1.5;">{safe_footer}</p>
</td></tr></table>
<p style="max-width:560px;margin:16px 0 0;color:#71839a;font-size:12px;line-height:1.5;">RiskSense AI · Account security notification</p>
</td></tr></table></body></html>"""


def registration_code_email(code: str) -> EmailContent:
    text = (
        "Your RiskSense AI verification code is:\n\n"
        f"{code}\n\n"
        "Enter this code in the app to verify your email address. It expires in 10 minutes.\n\n"
        "If you did not request this, ignore this email."
    )
    return EmailContent(text, _layout(
        title="Verify your email address",
        introduction="Enter the verification code below in the RiskSense AI app to continue registration.",
        value=code, label="Your verification code",
        explanation="This code expires in 10 minutes. Request a new code in the app if it expires.",
        footer="If you did not request this email, you can safely ignore it.",
        is_code=True,
    ))


def recovery_code_email(code: str) -> EmailContent:
    text = (
        "Your RiskSense AI password recovery code is:\n\n"
        f"{code}\n\n"
        "Enter this code in the app to reset your password. It expires in 10 minutes.\n\n"
        "If you did not request this, ignore this email."
    )
    return EmailContent(text, _layout(
        title="Reset your password",
        introduction="Enter the recovery code below in the RiskSense AI app to continue your password reset.",
        value=code, label="Your recovery code",
        explanation="This code expires in 10 minutes. Request another code in the app if it expires.",
        footer="If you did not request a password reset, you can safely ignore this email.",
        is_code=True,
    ))


def replacement_password_email(password: str) -> EmailContent:
    text = (
        "Your temporary RiskSense AI password is:\n\n"
        f"{password}\n\n"
        "Sign in with this password, then change it in Settings > Change Password.\n\n"
        "If you did not request this, contact RiskSense AI support immediately."
    )
    return EmailContent(text, _layout(
        title="Your replacement password",
        introduction="Your password reset is complete. Use the temporary password below to sign in.",
        value=password, label="Temporary password",
        explanation="After signing in, open Settings > Change Password and choose a password only you know.",
        footer="If you did not request this change, contact RiskSense AI support immediately.",
        is_code=False,
    ))


def clinician_change_decision_email(*, approved: bool, patient_name: str,
        old_name: str, old_institution: str | None, old_id: str,
        new_name: str, new_institution: str | None, new_id: str) -> EmailContent:
    """Notify a patient of an admin-reviewed clinician link decision."""
    if not approved:
        text = (
            f"Hello {patient_name},\n\n"
            "Your request to change your linked clinician was not approved. "
            "Your current clinician remains linked to your RiskSense AI account.\n\n"
            "If you believe this is an error, contact RiskSense AI support or submit a new request in Settings."
        )
        return EmailContent(text, _layout(
            title="Clinician change request not approved",
            introduction=f"Hello {patient_name}, your request to change your linked clinician was reviewed.",
            value="Not approved", label="Request status",
            explanation="Your current clinician remains linked to your account. You can submit a new request in Settings if needed.",
            footer="If you believe this decision is incorrect, contact RiskSense AI support.",
            is_code=False,
        ))

    old_institution = old_institution or "Institution not recorded"
    new_institution = new_institution or "Institution not recorded"
    text = (
        f"Hello {patient_name},\n\n"
        "Your request to change your linked clinician has been approved.\n\n"
        f"Previous clinician: {old_name}\nInstitution: {old_institution}\nRiskSense ID: {old_id}\n\n"
        f"New linked clinician: {new_name}\nInstitution: {new_institution}\nRiskSense ID: {new_id}\n\n"
        "Your previous clinician's account access through this link has ended. "
        "You can view your new linked clinician in Settings."
    )
    def card(label: str, name: str, institution: str, clinician_id: str) -> str:
        return f'''<tr><td style="padding:0 30px 14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef8fc;border:1px solid #c8e8f3;border-radius:16px;"><tr><td style="padding:18px 20px;">
<p style="margin:0 0 9px;color:#52667c;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">{escape(label)}</p>
<p style="margin:0 0 5px;color:#08255b;font-size:20px;font-weight:700;">{escape(name)}</p>
<p style="margin:0 0 4px;color:#425672;font-size:14px;">{escape(institution)}</p>
<p style="margin:0;color:#52667c;font-size:13px;">RiskSense ID: {escape(clinician_id)}</p>
</td></tr></table></td></tr>'''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Clinician change approved</title></head>
<body style="margin:0;padding:0;background:#edf4fa;color:#102244;font-family:Arial,Helvetica,sans-serif;"><table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#edf4fa;padding:28px 12px;"><tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;background:#ffffff;border:1px solid #d5e6f2;border-radius:20px;overflow:hidden;">
<tr><td style="padding:25px 30px;background:#061b43;color:#ffffff;font-size:21px;font-weight:700;">RiskSense <span style="color:#83d5ef;">AI</span></td></tr>
<tr><td style="padding:30px 30px 24px;"><h1 style="margin:0 0 12px;font-size:25px;line-height:1.25;color:#102244;">Clinician change approved</h1><p style="margin:0;color:#425672;font-size:16px;line-height:1.55;">Hello {escape(patient_name)}, your request has been approved. Your linked clinician is now:</p></td></tr>
{card('New linked clinician', new_name, new_institution, new_id)}
{card('Previous clinician', old_name, old_institution, old_id)}
<tr><td style="padding:6px 30px 28px;"><p style="margin:0;color:#425672;font-size:14px;line-height:1.6;">Your previous clinician's access through this link has ended. View your linked clinician in the RiskSense AI app under Settings.</p><p style="margin:18px 0 0;padding-top:16px;border-top:1px solid #e4ecf4;color:#68788d;font-size:12px;">If you did not request this change, contact RiskSense AI support.</p></td></tr>
</table></td></tr></table></body></html>'''
    return EmailContent(text, html)


def elevated_risk_email(*, model_name: str, score: float,
                        factors: list[tuple[str, str]], previous_score: float | None,
                        model_version_changed: bool = False) -> EmailContent:
    """Email a persisted model estimate without exposing raw clinical inputs."""
    score_text = f"{score * 100:.1f}%"
    if previous_score is None:
        comparison = f"No previous {model_name} score is available for comparison."
    else:
        difference = (score - previous_score) * 100
        direction = "higher" if difference > 0 else "lower" if difference < 0 else "unchanged"
        comparison = (
            f"Previous {model_name} score: {previous_score * 100:.1f}%. "
            f"This score is {abs(difference):.1f} percentage points {direction}."
        )
        if model_version_changed:
            comparison += " The model version changed, so these scores may not be directly comparable."
    factor_lines = [f"- {label}: {direction} the model estimate" for label, direction in factors]
    factor_text = "\n".join(factor_lines) if factor_lines else "No contributing factors were available."
    text = (
        f"RiskSense AI {model_name} result\n\n"
        f"Elevated model score: {score_text}\n\n"
        f"Contributing factors (model calculations, not clinical causes):\n{factor_text}\n\n"
        f"{comparison}\n\n"
        "Open the RiskSense AI app to review the full analysis and discuss it with your clinician. "
        "This estimate does not diagnose a condition or replace professional medical advice.\n\n"
        "You can turn off these emails in Settings > Risk Result Alerts."
    )
    factor_items = "".join(
        '<li style="margin:0 0 8px;line-height:1.5;">'
        f'<strong>{escape(label)}</strong>: {escape(direction)} the model estimate</li>'
        for label, direction in factors
    ) or '<li style="line-height:1.5;">No contributing factors were available.</li>'
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RiskSense AI {escape(model_name)} result</title></head>
<body style="margin:0;padding:0;background:#edf4fa;color:#102244;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#edf4fa;padding:28px 12px;"><tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;background:#ffffff;border:1px solid #d5e6f2;border-radius:20px;overflow:hidden;">
<tr><td style="padding:25px 30px;background:#061b43;color:#ffffff;font-size:21px;font-weight:700;">RiskSense <span style="color:#83d5ef;">AI</span></td></tr>
<tr><td style="padding:28px 30px 12px;"><h1 style="margin:0 0 12px;font-size:24px;line-height:1.3;">Elevated {escape(model_name)} estimate</h1>
<p style="margin:0;color:#425672;font-size:15px;line-height:1.6;">A new risk analysis was saved to your account. Review the full result in the app.</p></td></tr>
<tr><td style="padding:16px 30px 22px;"><table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#eef8fc;border:1px solid #c8e8f3;border-radius:16px;"><tr><td align="center" style="padding:20px 12px;">
<p style="margin:0 0 9px;color:#52667c;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;">Estimated risk score</p>
<div style="font-size:36px;font-weight:800;color:#08255b;line-height:1.2;">{score_text}</div>
</td></tr></table></td></tr>
<tr><td style="padding:0 30px 25px;"><h2 style="margin:0 0 10px;font-size:17px;">Contributing factors</h2>
<p style="margin:0 0 12px;color:#52667c;font-size:13px;line-height:1.5;">These describe model calculations relative to its training baseline. They are not clinical causes.</p>
<ul style="margin:0 0 22px;padding-left:20px;color:#334864;font-size:14px;">{factor_items}</ul>
<div style="padding:15px;border-radius:12px;background:#f2f6fa;color:#334864;font-size:14px;line-height:1.5;">{escape(comparison)}</div>
<p style="margin:22px 0 0;color:#425672;font-size:14px;line-height:1.6;">Open the RiskSense AI app to review the full analysis and discuss it with your clinician.</p>
<p style="margin:18px 0 0;padding-top:16px;border-top:1px solid #e4ecf4;color:#68788d;font-size:12px;line-height:1.5;">RiskSense AI provides decision-support estimates. This result is not a diagnosis or medical advice. Manage these emails in Settings &gt; Risk Result Alerts.</p>
</td></tr></table></td></tr></table></body></html>"""
    return EmailContent(text, html)
