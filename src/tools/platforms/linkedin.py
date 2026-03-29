"""
src/tools/platforms/linkedin.py
───────────────────────────────
LinkedIn Job Postings API Client.
"""
from __future__ import annotations
import requests
from loguru import logger
from src.config import settings

class LinkedInClient:
    def __init__(self):
        self.access_token = settings.linkedin_access_token
        self.base_url = "https://api.linkedin.com/v2"

    def publish_job(self, job_id: str, job_title: str, jd_content: str) -> str:
        """
        Post JD to LinkedIn via the modern Posts API.
        Reference: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/posts-api
        """
        if not self.access_token or self.access_token == "your_linkedin_access_token":
            logger.warning("🧪 [LinkedIn] No access token found. Simulating successful post.")
            return f"https://www.linkedin.com/jobs/view/mock-{job_id}"

        logger.info("🔗 [LinkedIn] Posting job update for: {}", job_title)
        
        # Modern Posts API endpoint (restli version 2.0.0)
        url = "https://api.linkedin.com/rest/posts"
        
        # LinkedIn allows ~3000 chars for post commentary. Truncate at 2900 to be safe.
        summary = f"🚀 WE ARE HIRING: {job_title}\n\n{jd_content[:2900]}"
        
        arn = str(settings.linkedin_company_urn)
        author_urn = arn if arn.startswith("urn:li:") else f"urn:li:organization:{arn}"
        
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
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202602", # Required for versioned APIs
            "X-Restli-Protocol-Version": "2.0.0"
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            
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
                
                logger.success("✅ [LinkedIn] Published: {}", post_url)
                return post_url
            else:
                logger.error("❌ [LinkedIn] API failed ({}): {}", response.status_code, response.text)
                return f"ERROR: LinkedIn API failed ({response.status_code}): {response.text}"
            
        except Exception as e:
            logger.error("❌ [LinkedIn] Exception: {}", e)
            return f"ERROR: LinkedIn communication error: {e}"
