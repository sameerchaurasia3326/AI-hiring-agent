"""
src/utils/config_builder.py
────────────────────────────
Step 8: The only place in the email system where global 'settings' are accessed.
Bridges the configuration to the pure email_utils dispatcher.
"""
from typing import Dict, Any
# Only import settings here
from src.config.settings import settings

def build_email_config(settings: Any) -> Dict[str, Any]:
    """
    Builds the structured configuration dictionary required by email_utils.send_any_email.
    Strictly follows the requirement in Step 8 signature request.
    """
    return {
        "resend": {
            "api_key": settings.resend_api_key,
            "from_email": settings.from_email
        },
        "smtp": {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "email": settings.smtp_email,
            "password": settings.smtp_password
        }
    }

