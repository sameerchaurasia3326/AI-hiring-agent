import asyncio
import sys

# Ensure the root directory is on the path so we can import src
sys.path.insert(0, "/Users/sameer/Documents/hiring.ai")

from src.utils.email_utils import send_any_email
from loguru import logger

async def run_tests():
    print("=" * 60)
    print("TEST 1: Resend Success (Verified Email)")
    print("-" * 60)
    # The owner email should succeed via Resend
    await send_any_email("projectsmtp64@gmail.com", "TEST 1", "Resend Test")

    print("\n" + "=" * 60)
    print("TEST 2: Resend Failure \u2192 SMTP Fallback (Unverified Email)")
    print("-" * 60)
    # This email will be blocked by Resend, testing the SMTP fallback and [EMAIL] logic
    await send_any_email("sameerchaurasia3326@gmail.com", "TEST 2", "SMTP Fallback Test")

    print("\n" + "=" * 60)
    print("TEST 3: Both Fail (Invalid Format Simulation)")
    print("-" * 60)
    # Using an invalid string causes both providers to fail
    await send_any_email("not-an-email", "TEST 3", "Total Failure Test")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())
