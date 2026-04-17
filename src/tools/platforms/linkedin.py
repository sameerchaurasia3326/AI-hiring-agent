"""
src/tools/platforms/linkedin.py
───────────────────────────────
LinkedIn Job Postings API Client.
"""
from __future__ import annotations
import requests
from loguru import logger
from src.config import settings

import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Job, Integration, Organization, Activity

async def refresh_linkedin_token(integration: Integration, db: AsyncSession) -> bool:
    import httpx
    from datetime import datetime, timezone, timedelta
    from src.config import settings
    from loguru import logger
    from src.utils.crypto import encrypt_token, decrypt_token
    
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    decrypted_refresh = decrypt_token(integration.refresh_token) if integration.refresh_token else None
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": decrypted_refresh,
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(token_url, data=data)
            if resp.status_code == 200:
                resp_data = resp.json()
                new_access = resp_data.get("access_token")
                if new_access:
                    integration.access_token = encrypt_token(new_access)
                
                # Update refresh token if provided
                if "refresh_token" in resp_data:
                    integration.refresh_token = encrypt_token(resp_data["refresh_token"])
                    
                expires_in = resp_data.get("expires_in")
                if expires_in:
                    integration.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                
                await db.commit()
                logger.info("✅ [LinkedIn] Successfully refreshed access token for Org {}", integration.organization_id)
                return True
            else:
                logger.error("❌ [LinkedIn] Failed to refresh token: {}", resp.text)
                return False
    except Exception as e:
        logger.error("❌ [LinkedIn] Exception refreshing token: {}", e)
        return False

class LinkedInClient:
    def __init__(self):
        self.base_url = "https://api.linkedin.com/v2"

    async def publish_job(self, job_id: str, job_title: str, jd_content: str, db: AsyncSession) -> str:
        """
        Post JD to LinkedIn via the modern Posts API.
        Reference: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
        """
        # 1. Fetch Job (with FOR UPDATE to block parallel Celery workers posting simultaneously)
        stmt = select(Job).where(Job.id == job_id).with_for_update()
        res = await db.execute(stmt)
        job = res.scalars().first()
        
        if not job or not job.organization_id:
            logger.error("❌ [LinkedIn] Job {} not found or missing organization_id", job_id)
            return "LinkedIn not ready for this organization"
            
        # Idempotency check: Don't double post if celery retries
        if job.external_post_id:
            logger.info("ℹ️ [LinkedIn] Job {} already posted natively (external_post_id={}). Skipping.", job.id, job.external_post_id)
            return f"https://www.linkedin.com/feed/update/{job.external_post_id}"
            
        # Fetch organization name for logging
        stmt_org = select(Organization).where(Organization.id == job.organization_id)
        res_org = await db.execute(stmt_org)
        org = res_org.scalars().first()
        org_name = org.name if org else str(job.organization_id)
            
        # 2. Query Integration
        stmt_int = select(Integration).where(
            Integration.organization_id == job.organization_id,
            Integration.provider == "linkedin"
        )
        res_int = await db.execute(stmt_int)
        integration = res_int.scalars().first()
        
        # 3. If not found, check fallback
        if not integration or not integration.access_token:
            if getattr(settings, "linkedin_fallback_enabled", False):
                logger.warning("⚠️ [LinkedIn] No Integration found. Using global settings (fallback enabled).")
                access_token = settings.linkedin_access_token
                company_urn = str(settings.linkedin_company_urn)
            else:
                logger.error("❌ [LinkedIn] LinkedIn not connected for this organization")
                return "LinkedIn not ready for this organization"
        else:
            # 3.5 Check expiry and refresh if needed
            from datetime import datetime, timezone
            if integration.expires_at and integration.expires_at < datetime.now(timezone.utc):
                logger.info("⏳ [LinkedIn] Token expired. Attempting refresh...")
                if not integration.refresh_token:
                    logger.error("❌ [LinkedIn] Token expired and no refresh_token available")
                    return "LinkedIn not ready for this organization"
                
                success = await refresh_linkedin_token(integration, db)
                if not success:
                    # Mark integration as invalid
                    integration.access_token = None
                    integration.status = "expired"
                    await db.commit()
                    return "LinkedIn not ready for this organization"
                    
            # 4. Extract tokens
            from src.utils.crypto import decrypt_token
            access_token = decrypt_token(integration.access_token) if integration.access_token else None
            metadata = integration.provider_metadata or {}
            company_urn = metadata.get("company_urn")
            account_sub = metadata.get("account_sub")
            
        if not access_token or str(access_token).strip() == "":
            return "LinkedIn not ready for this organization"
            
        if integration and getattr(integration, "status", None) != "active":
            logger.error("❌ [LinkedIn] Integration status is not active (status={})", getattr(integration, "status", None))
            return "LinkedIn not ready for this organization"
            
        author_urn = None
        if company_urn:
            author_urn = company_urn if company_urn.startswith("urn:li:") else f"urn:li:organization:{company_urn}"
        elif account_sub:
            author_urn = f"urn:li:person:{account_sub}"
            
        if not author_urn:
            logger.warning("⚠️ [LinkedIn] Missing both company_urn and account_sub for Org {}", job.organization_id)
            return "LinkedIn not ready for this organization"

        logger.info("🔗 [LinkedIn] Posting job update for: {} using author {}", job_title, author_urn)
        
        # Modern Posts API endpoint (restli version 2.0.0)
        url = "https://api.linkedin.com/rest/posts"
        
        # LinkedIn allows ~3000 chars for post commentary. Truncate safely.
        email_to_apply = job.hiring_manager_email or "hr@hiring.ai"
        instruction = f"\n\n👉 HOW TO APPLY:\nPlease email your resume to {email_to_apply} to submit your application."
        
        safe_jd_len = 2900 - len(instruction)
        summary = f"🚀 WE ARE HIRING: {job_title}\n\n{jd_content[:safe_jd_len]}...{instruction}"
        
        payload = {
            "author": author_urn,
            "commentary": summary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202602", # Required for versioned APIs
            "X-Restli-Protocol-Version": "2.0.0"
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
            
            # API might return 201 Created
            if response.status_code in [200, 201]:
                # The ID is in the X-RestLi-Id header or response body
                li_id = response.headers.get("X-RestLi-Id", "completed")
                post_url = f"https://www.linkedin.com/feed/update/{li_id}"
                
                # Bright terminal output for the user
                print("\n" + "⭐"*50)
                print(f"🚀 [LINKEDIN] POST SUCCESSFULLY DONE!")
                print(f"🔗 URL: {post_url}")
                print("⭐"*50 + "\n")
                
                # Save the post ID to prevent duplicates on retries
                job.external_post_id = li_id
                
                # Log success activity
                act = Activity(
                    organization_id=job.organization_id,
                    job_id=job.id,
                    message=f"Job posted to LinkedIn for {org_name}",
                    type="linkedin_posted"
                )
                db.add(act)
                await db.commit()
                
                import json
                logger.info(json.dumps({
                    "event": "linkedin_post",
                    "job_id": str(job.id),
                    "organization_id": str(job.organization_id),
                    "status": "success"
                }))
                
                logger.success("✅ [LinkedIn] Published: {}", post_url)
                return post_url
            elif response.status_code == 429:
                error_msg = "Rate limit hit (429 Too Many Requests)"
                import json
                logger.info(json.dumps({
                    "event": "linkedin_post",
                    "job_id": str(job.id),
                    "organization_id": str(job.organization_id),
                    "status": "failed",
                    "error": "rate_limit"
                }))
                logger.error("⏳ [LinkedIn] {}", error_msg)
                raise Exception(error_msg)
            else:
                error_msg = f"API failed ({response.status_code}): {response.text}"
                act = Activity(
                    organization_id=job.organization_id,
                    job_id=job.id,
                    message=f"LinkedIn posting failed for Org {job.organization_id} (Job {job.id}): {error_msg}",
                    type="linkedin_failed"
                )
                db.add(act)
                await db.commit()
                
                import json
                logger.info(json.dumps({
                    "event": "linkedin_post",
                    "job_id": str(job.id),
                    "organization_id": str(job.organization_id),
                    "status": "failed",
                    "error": str(response.status_code)
                }))
                
                logger.error("❌ [LinkedIn] {}", error_msg)
                if 'integration' in locals() and integration:
                    integration.status = "error"
                    await db.commit()
                raise Exception(error_msg)
            
        except Exception as e:
            # Re-raise directly if it's our structured raised error from above
            if "API failed (" in str(e) or "Rate limit hit" in str(e):
                raise e
            
            act = Activity(
                organization_id=job.organization_id,
                job_id=job.id,
                message=f"LinkedIn posting failed for Org {job.organization_id} (Job {job.id}): {str(e)}",
                type="linkedin_failed"
            )
            db.add(act)
            await db.commit()
            
            import json
            logger.info(json.dumps({
                "event": "linkedin_post",
                "job_id": str(job.id),
                "organization_id": str(job.organization_id),
                "status": "failed",
                "error": "exception"
            }))
            
            logger.error("❌ [LinkedIn] Exception: {}", e)
            if 'integration' in locals() and integration:
                integration.status = "error"
                await db.commit()
            raise e
