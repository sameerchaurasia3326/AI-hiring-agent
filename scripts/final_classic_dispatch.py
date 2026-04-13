import asyncio
import uuid
from src.db.database import AsyncSessionLocal
from src.db.models import Job, Outbox
from sqlalchemy import delete, select
from src.utils.email_utils import send_any_email
from src.utils.config_builder import build_email_config
from src.config.settings import settings

async def main():
    job_id = uuid.UUID("b4e069df-5f95-4916-b0c4-1517bd5a3fc5")
    async with AsyncSessionLocal() as session:
        # 1. Clear old state
        print("🧹 Clearing old outbox items for this job...")
        await session.execute(delete(Outbox).where(Outbox.job_id == job_id))
        await session.commit()
        
        # 2. Get Job Details for Payload
        res = await session.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()
        if not job:
            print("❌ Job not found.")
            return
            
        payload = {
            "email": job.hiring_manager_email,
            "name": job.hiring_manager_name or "Hiring Manager",
            "job_title": job.title,
            "department": job.department or "Engineering",
            "full_jd": job.full_jd or job.jd_draft or "No content available.",
        }
        
    # 3. Build the Classic Email (exactly matching Image 2 & 3)
    approve_url = f"http://localhost:8000/jobs/{job_id}/approve-jd?approved=true"
    reject_url = f"http://localhost:8000/jobs/{job_id}/approve-jd?approved=false"
    dashboard_url = f"http://localhost:5173/dashboard/jobs/{job_id}"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <div style="max-width: 700px; margin: 0 auto; padding: 40px 20px;">
            <div style="margin-bottom: 32px;">
                <h1 style="color: #2563eb; font-size: 20px; display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    📄 Job Description Draft Ready
                </h1>
                <p style="margin: 0; color: #4b5563; font-size: 14px;">
                    The AI has generated a complete JD for the <strong>{payload['job_title']}</strong> role ({payload['department']}).
                </p>
                <p style="margin: 8px 0 0 0; color: #9ca3af; font-size: 12px; font-weight: bold;">
                    Job ID: {job_id}
                </p>
            </div>

            <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 32px; margin-bottom: 32px; color: #1f2937; font-size: 15px; line-height: 1.6;">
                <div style="white-space: pre-wrap;">{payload['full_jd']}</div>
            </div>

            <div style="border-top: 2px solid #e5e7eb; padding-top: 32px;">
                <h3 style="display: flex; align-items: center; gap: 8px; margin: 0 0 12px 0; font-size: 16px; color: #000;">
                    ⚡ Action Required (Human-in-the-Loop)
                </h3>
                <p style="margin: 0 0 24px 0; color: #4b5563; font-size: 14px;">
                    The recruitment pipeline is currently <strong>paused</strong> waiting for your decision.
                </p>

                <div style="display: flex; gap: 12px; margin-bottom: 24px;">
                    <a href="{approve_url}" style="background: #10b981; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: bold; display: inline-block;">
                        ✅ Approve & Publish JD
                    </a>
                    <a href="{reject_url}" style="background: #f59e0b; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: bold; display: inline-block;">
                        🔄 Review & Request Revision
                    </a>
                </div>

                <p style="margin: 0; color: #6b7280; font-size: 13px;">
                    Alternatively, to request AI revisions or manually edit the draft, <a href="{dashboard_url}" style="color: #2563eb; text-decoration: none;">visit your HR Dashboard &rarr;</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    config = build_email_config(settings)
    print(f"📧 Sending Classic JD email to {payload['email']}...")
    success = await send_any_email(
        to=payload["email"],
        subject=f"[Hiring AI] Review Required: {payload['job_title']}",
        html=html,
        provider="resend",
        config=config,
        fallback=True
    )
    if success:
        print("✅ [SUCCESS] Perfectly restored JD email sent successfully!")
        # Also mark outbox as done so the scheduler doesn't double-send later
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Outbox).where(Outbox.job_id == job_id))
            await session.commit()
    else:
        print("❌ [FAILURE] Final dispatch failed.")

if __name__ == "__main__":
    asyncio.run(main())
