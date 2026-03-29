import resend
from src.config import settings
from loguru import logger

def test_resend():
    logger.info("🧪 Testing Resend connection...")
    if not settings.resend_api_key or settings.resend_api_key.startswith("re_xxx"):
        logger.error("❌ Resend API Key is not set in .env")
        return

    resend.api_key = settings.resend_api_key
    
    try:
        params = {
            "from": settings.from_email,
            "to": settings.hr_email,
            "subject": "🧪 Hiring AI - Resend Test",
            "text": "This is a test email from your AI Hiring Agent! If you see this, Resend is working.",
        }
        resend.Emails.send(params)
        logger.success("✅ Resend Test Email Sent! Check your inbox.")
    except Exception as e:
        logger.error("❌ Resend Test Failed: {}", e)

if __name__ == "__main__":
    test_resend()
