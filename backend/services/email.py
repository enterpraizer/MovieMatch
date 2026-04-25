"""Email delivery for verification links.

Two modes, chosen implicitly by whether SMTP_HOST is set:

- **dev**  (SMTP_HOST empty) — the verification link is logged via structlog so
  you can grab it from /tmp/mm-backend.log.
- **prod** (SMTP_HOST set)   — sends a real email via aiosmtplib with STARTTLS.

For Gmail:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=you@gmail.com
  SMTP_PASSWORD=<app password, 16 chars>
"""
from urllib.parse import quote_plus

import structlog

from config import get_settings


async def send_verification_email(to_email: str, token: str) -> None:
    settings = get_settings()
    link = (
        f"{settings.public_app_url}/verify?token={token}"
        f"&email={quote_plus(to_email)}"
    )
    log = structlog.get_logger()

    if not settings.smtp_host:
        # Dev mode — just print the link so it's trivially grep-able.
        log.info(
            "email_verification_link_DEV",
            to=to_email,
            link=link,
            expires_in_min=settings.email_verification_ttl_minutes,
        )
        return

    try:
        import aiosmtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = to_email
        msg["Subject"] = "Verify your MovieMatch email"
        msg.set_content(
            "Welcome to MovieMatch!\n\n"
            f"Click the link below to verify your email — it expires in "
            f"{settings.email_verification_ttl_minutes} minutes:\n\n"
            f"{link}\n\n"
            "If you didn't sign up, ignore this email."
        )
        msg.add_alternative(
            f"""
            <!doctype html><html><body style="font-family: sans-serif; max-width: 520px; margin: 2rem auto; color: #222;">
              <h2 style="color: #6d28d9;">Welcome to MovieMatch</h2>
              <p>Tap the button below to verify your email.
                 The link is valid for {settings.email_verification_ttl_minutes} minutes.</p>
              <p>
                <a href="{link}" style="display: inline-block; background: #6d28d9; color: white;
                   padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                  Verify email
                </a>
              </p>
              <p style="color: #666; font-size: 12px;">Or paste this URL into your browser:<br>
                <a href="{link}">{link}</a>
              </p>
              <p style="color: #999; font-size: 11px;">If you didn't sign up for MovieMatch, you can ignore this message.</p>
            </body></html>
            """.strip(),
            subtype="html",
        )

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_start_tls,
        )
        log.info("email_verification_sent", to=to_email)
    except Exception as e:
        # We never want registration to hard-fail just because SMTP hiccupped.
        # User can request a resend from the UI.
        log.warning("email_verification_send_failed", to=to_email, error=str(e))
