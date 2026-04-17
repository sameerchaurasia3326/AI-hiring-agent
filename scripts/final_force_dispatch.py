import asyncio
from src.db.database import AsyncSessionLocal
from src.db.models import Outbox
from sqlalchemy import select, update
import sys

async def main():
    try:
        from src.utils.email_utils import send_any_email
        from src.utils.config_builder import build_email_config
        from src.config.settings import settings
        
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(Outbox).where(Outbox.type == "JD_APPROVAL_REQUEST").order_by(Outbox.created_at.desc()).limit(1)
            )
            item = res.scalar_one_or_none()
            if not item:
                print("❌ ITEM_NOT_FOUND")
                return

            print(f"📦 Resetting item {item.id} to PENDING...")
            item.status = "PENDING"
            item.retry_count = 0
            await session.commit()
            
            payload = item.payload
            target = payload.get("email")
            subject = f"[Hiring AI] Action Required: Approve JD for {payload.get('job_title')}"
            
            # Use the actual dispatcher directly to avoid loop conflicts
            email_config = build_email_config(settings)
            
            print(f"📧 Sending to {target} via Resend (manual)...")
            success = await send_any_email(
                to=target,
                subject=subject,
                html="JD Approval Required. Please check the dashboard.", # Simplified for test
                provider="resend",
                config=email_config,
                fallback=True
            )
            
            if success:
                item.status = "SENT"
                await session.commit()
                print("✅ [SUCCESS] Email sent successfully.")
            else:
                print("❌ [FAILURE] Dispatcher returned False.")
                
    except Exception as e:
        print(f"❌ [ERROR] {e}")

if __name__ == "__main__":
    asyncio.run(main())
