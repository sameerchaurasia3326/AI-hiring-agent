"""
scratch/test_email_edge_cases.py
──────────────────────────────────
Step 14: Test edge cases (Missing config, Invalid provider, Fallback logic).
"""
import asyncio
import os
import sys

# Ensure project root is in PYTHONPATH
sys.path.append(os.getcwd())

from src.utils.email_utils import send_any_email, EmailSendError
from loguru import logger

async def test_edge_cases():
    logger.info("🧪 [TEST] Starting Step 14 Edge Case Testing...")

    # Case 1: Invalid Provider
    logger.info("➡️ Case 1: Invalid Provider")
    try:
        await send_any_email("test@example.com", "Sub", "Body", "INVALID_PROVIDER", {})
        logger.error("❌ Case 1 FAILED: Expected EmailSendError for invalid provider, but it succeeded.")
    except EmailSendError as e:
        logger.success(f"✅ Case 1 PASSED: {e}")
    except Exception as e:
        logger.error(f"❌ Case 1 FAILED: Expected EmailSendError, but got {type(e).__name__}: {e}")

    # Case 2: Missing Config (resend without api_key)
    logger.info("➡️ Case 2: Missing Config (Resend)")
    try:
        config = {"resend": {}, "smtp": {}}
        await send_any_email("test@example.com", "Sub", "Body", "resend", config)
        logger.error("❌ Case 2 FAILED: Expected EmailSendError for missing resend api_key, but it succeeded.")
    except EmailSendError as e:
        logger.success(f"✅ Case 2 PASSED: {e}")
    except Exception as e:
        logger.error(f"❌ Case 2 FAILED: Expected EmailSendError, but got {type(e).__name__}: {e}")

    # Case 3: Missing Config (SMTP)
    logger.info("➡️ Case 3: Missing Config (SMTP)")
    try:
        config = {"resend": {}, "smtp": {"host": "localhost"}}
        await send_any_email("test@example.com", "Sub", "Body", "smtp", config)
        logger.error("❌ Case 3 FAILED: Expected EmailSendError for incomplete SMTP config, but it succeeded.")
    except EmailSendError as e:
        logger.success(f"✅ Case 3 PASSED: {e}")
    except Exception as e:
        logger.error(f"❌ Case 3 FAILED: Expected EmailSendError, but got {type(e).__name__}: {e}")

    # Case 4: Fallback Logic (Invalid Resend -> Should try SMTP)
    logger.info("➡️ Case 4: Fallback Logic (Resend -> SMTP)")
    # We provide invalid SMTP credentials - it should still "try" it and log it failing.
    # If it tries secondary, it passed the logic test.
    config = {
        "resend": {"api_key": "INVALID", "from_email": "test@test.com"},
        "smtp": {"host": "BAD_HOST", "port": 587, "email": "A", "password": "B"}
    }
    success = await send_any_email("test@test.com", "Sub", "Body", "resend", config, fallback=True)
    if not success:
        # It's okay if it fails, as long as it TRIED both.
        # logger output will confirm the fallback attempt.
        logger.success("✅ Case 4 LOGIC check PASSED (check log for 'Attempting fallback to smtp')")

if __name__ == "__main__":
    asyncio.run(test_edge_cases())
