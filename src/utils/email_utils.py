"""
src/utils/email_utils.py
─────────────────────────
Purified email system (Steps 1-7, 11).
No global settings imports. Pure functions only.
"""
import smtplib
from email.mime.text import MIMEText
import asyncio
import httpx
from loguru import logger
from typing import Optional, Dict, Any


class EmailSendError(Exception):
    pass


async def _send_via_resend(
    to: str, 
    subject: str, 
    html: bool, 
    api_key: str, 
    from_email: str
) -> bool:
    """Step 3: Refactored Resend dispatcher with strict validation and no global settings."""
    if not api_key:
        raise EmailSendError("api_key is required for Resend provider")
    if not from_email:
        raise EmailSendError("from_email is required for Resend provider")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {
                "from": f"Hiring AI <{from_email}>",
                "to": [to] if isinstance(to, str) else to,
                "subject": subject,
            }
            if html:
                payload["html"] = html if isinstance(html, str) else subject # Safety check
            else:
                payload["text"] = str(html) # Fallback if only one body provided
            
            # Re-read: The step says logic used to be (to, subject, html, api_key, from_email)
            # The 'html' parameter contains the body content.
            # Normalizing signature expectations: html is the body.
            payload["html" if html else "text"] = html

            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if response.status_code >= 400:
            logger.warning(f"[EMAIL:Resend] Failed with status {response.status_code}: {response.text}")
            return False

        logger.info(f"[EMAIL:Resend] Successfully sent to {to}")
        return True

    except Exception as e:
        logger.warning("[EMAIL:Resend] Error: {}", e)
        return False


async def _send_via_smtp(
    to: str, 
    subject: str, 
    html: bool, 
    smtp_host: str, 
    smtp_port: int, 
    smtp_email: str, 
    smtp_password: str
) -> bool:
    """Step 4: Refactored SMTP dispatcher with strict validation."""
    if not all([smtp_host, smtp_port, smtp_email, smtp_password]):
        raise EmailSendError("Missing required SMTP configuration (host, port, email, or password)")

    def _sync_send():
        content_type = "html" if html else "plain"
        msg = MIMEText(str(html), content_type)
        msg["Subject"] = subject
        msg["From"] = smtp_email
        msg["To"] = to if isinstance(to, str) else ", ".join(to)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)

    try:
        await asyncio.to_thread(_sync_send)
        logger.info(f"[EMAIL:SMTP] Successfully sent to {to}")
        return True
    except Exception as e:
        logger.error("[EMAIL:SMTP] Error: {}", e)
        return False


async def send_any_email(
    to: str, 
    subject: str, 
    html: str, 
    provider: str, 
    config: Dict[str, Any], 
    fallback: bool = False
) -> bool:
    """
    Step 5-6: Refactored pure failover dispatcher.
    New signature: (to, subject, html, provider, config, fallback=False)
    """
    if provider not in ["resend", "smtp"]:
        logger.error(f"❌ Invalid provider requested: {provider}")
        raise EmailSendError(f"Unsupported provider: {provider}")

    logger.info(f"📧 Starting email dispatch via {provider} to {to} (fallback={fallback})")

    async def _dispatch(current_provider: str) -> bool:
        if current_provider == "resend":
            r_conf = config.get("resend", {})
            return await _send_via_resend(
                to=to,
                subject=subject,
                html=html,
                api_key=r_conf.get("api_key"),
                from_email=r_conf.get("from_email")
            )
        elif current_provider == "smtp":
            s_conf = config.get("smtp", {})
            return await _send_via_smtp(
                to=to,
                subject=subject,
                html=html,
                smtp_host=s_conf.get("host"),
                smtp_port=s_conf.get("port"),
                smtp_email=s_conf.get("email"),
                smtp_password=s_conf.get("password")
            )
        return False

    # 1. Try Primary
    success = await _dispatch(provider)
    if success:
        return True

    # 2. Try Fallback (Step 6)
    if fallback:
        secondary = "smtp" if provider == "resend" else "resend"
        logger.info(f"🔄 Primary provider {provider} failed. Attempting fallback to {secondary}...")
        return await _dispatch(secondary)

    return False


async def send_otp_email(email: str, otp: str, config: Dict[str, Any]):
    """Refactored OTP helper to take config explicitly."""
    subject = "Verify your email"
    body = f"Your OTP is: {otp} (valid for 10 minutes)"
    # Defaulting OTPs to Resend with SMTP fallback
    await send_any_email(email, subject, body, "resend", config, fallback=True)
